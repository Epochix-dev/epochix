"""/sse/live/{run_id}, read as a browser's EventSource reads it.

The dashboard's fallback for a proxy that refuses the WebSocket upgrade. No
test had ever requested the route. These drive a real `epochix --live` run fed
line by line, and read the server's stream over a socket while the run is
still going.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import uvicorn

from epochix.config import Settings
from epochix.server import sse
from epochix.server.app import create_app
from tests.live_cli import LiveCli, epoch_line, free_port

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class Event:
    id: str | None
    data: dict[str, object] | None
    comment: str | None


@dataclass
class Stream:
    """One /sse/live connection, read on its own thread."""

    status: int = 0
    content_type: str | None = None
    events: list[Event] = field(default_factory=list)
    ended: threading.Event = field(default_factory=threading.Event)
    _conn: http.client.HTTPConnection | None = None

    def typed(self) -> list[tuple[str, int]]:
        return [(str(e.data["type"]), int(str(e.data["seq"]))) for e in self.events if e.data]

    def wait_for(self, predicate: object, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():  # type: ignore[operator]
                return
            time.sleep(0.05)
        raise AssertionError(f"not seen within {timeout} s; got {self.typed()}")

    def close(self) -> None:
        if self._conn is not None and self._conn.sock is not None:
            self._conn.sock.shutdown(socket.SHUT_RDWR)
            self._conn.close()


def open_stream(port: int, path: str, headers: dict[str, str] | None = None) -> Stream:
    stream = Stream()
    started = threading.Event()

    def read() -> None:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        stream._conn = conn
        try:
            conn.request("GET", path, headers={"Accept": "text/event-stream", **(headers or {})})
            resp = conn.getresponse()
            stream.status = resp.status
            stream.content_type = resp.getheader("content-type")
            started.set()
            buf = b""
            while True:
                chunk = resp.read1(65536)
                if not chunk:
                    return
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    ev = Event(id=None, data=None, comment=None)
                    for line in raw.decode("utf-8").splitlines():
                        if line.startswith("id: "):
                            ev.id = line[4:]
                        elif line.startswith("data: "):
                            ev.data = json.loads(line[6:])
                        elif line.startswith(":"):
                            ev.comment = line[1:].strip()
                    stream.events.append(ev)
        except OSError:
            return
        finally:
            started.set()
            stream.ended.set()

    threading.Thread(target=read, daemon=True).start()
    assert started.wait(15), "the stream did not answer"
    return stream


@pytest.fixture
def live(tmp_path: Path) -> Iterator[LiveCli]:
    cli = LiveCli(tmp_path)
    try:
        yield cli
    finally:
        cli.stop()


def _started_run(cli: LiveCli, epochs: int, of: int) -> str:
    cli.write(*(epoch_line(e, of) for e in range(1, epochs + 1)))
    run_id = cli.run_id()
    cli.wait_for_frames(run_id, 1)
    return run_id


def test_a_live_run_is_told_over_sse_while_it_runs(live: LiveCli) -> None:
    run_id = _started_run(live, 3, of=6)
    have = max(int(str(f["seq"])) for f in live.frames(run_id))

    stream = open_stream(live.port, f"/sse/live/{run_id}?last_seq={have}")
    assert stream.status == 200
    assert stream.content_type == "text/event-stream; charset=utf-8"

    live.write(epoch_line(4, of=6))
    stream.wait_for(lambda: any(t == "story_frame" for t, _ in stream.typed()))
    assert not stream.ended.is_set(), "the stream ended while the run was still going"
    assert live.proc.poll() is None

    live.write(epoch_line(5, of=6), epoch_line(6, of=6))
    assert live.finish() == 0
    assert stream.ended.wait(15), "the stream did not end when the run did"

    told = stream.typed()
    assert told[-1][0] == "complete", told
    stored = [int(str(f["seq"])) for f in _frames_after_finish(live, run_id)]
    sent = [seq for kind, seq in told if kind == "story_frame"]
    assert sent == [s for s in stored if s > have], (sent, stored)
    assert any(kind == "milestone" for kind, _ in told), told

    # Every frame, milestone and warning carries its seq as the event id, so a
    # browser that reconnects by itself says where it got to.
    for ev in stream.events:
        if ev.data and ev.data["type"] in {"story_frame", "milestone", "warning"}:
            assert ev.id == str(ev.data["seq"]), ev
        elif ev.data:
            assert ev.id is None, ev


def _frames_after_finish(cli: LiveCli, run_id: str) -> list[dict[str, object]]:
    from epochix.store.sqlite_store import RunStore

    return [f.model_dump(mode="json") for f in RunStore(str(cli.db)).get_story_frames(run_id)]


def test_a_reconnect_resumes_after_the_last_event_it_received(live: LiveCli) -> None:
    run_id = _started_run(live, 5, of=8)
    seqs = [int(str(f["seq"])) for f in live.frames(run_id)]
    assert len(seqs) >= 3, seqs
    middle = seqs[len(seqs) // 2]

    by_query = open_stream(live.port, f"/sse/live/{run_id}?last_seq={middle}")
    # EventSource reopens the URL it was opened with, and says how far it got
    # in Last-Event-ID; the URL's last_seq is where it first started.
    by_header = open_stream(
        live.port, f"/sse/live/{run_id}?last_seq=-1", headers={"Last-Event-ID": str(middle)}
    )
    expected = [s for s in seqs if s > middle]
    for stream in (by_query, by_header):
        stream.wait_for(
            lambda s=stream: [q for k, q in s.typed() if k == "story_frame"] == expected
        )
    for stream in (by_query, by_header):
        stream.close()


def test_without_a_last_seq_only_what_follows_is_sent(live: LiveCli) -> None:
    run_id = _started_run(live, 3, of=6)
    stream = open_stream(live.port, f"/sse/live/{run_id}")
    live.write(epoch_line(4, of=6))
    stream.wait_for(lambda: any(k == "story_frame" for k, _ in stream.typed()))
    held = {int(str(f["seq"])) for f in live.frames(run_id)}
    first = min(q for k, q in stream.typed() if k == "story_frame")
    assert first == max(held), (first, held)
    stream.close()


def test_the_feed_wants_the_token_when_one_is_set(tmp_path: Path) -> None:
    cli = LiveCli(tmp_path, env={"EPOCHIX_AUTH_TOKEN": "s3cret-for-this-test"})
    try:
        cli.write(*(epoch_line(e, 6) for e in range(1, 4)))
        # /api/runs wants the bearer token too.
        deadline = time.monotonic() + 30
        run_id = None
        while time.monotonic() < deadline and run_id is None:
            status, body = cli.get(
                "/api/runs", headers={"Authorization": "Bearer s3cret-for-this-test"}
            )
            if status == 200 and (runs := json.loads(body)["runs"]):
                run_id = runs[0]["id"]
            time.sleep(0.1)
        assert run_id, "no run appeared"

        assert cli.get(f"/sse/live/{run_id}")[0] == 401
        assert cli.get(f"/sse/live/{run_id}?token=wrong")[0] == 401
        stream = open_stream(cli.port, f"/sse/live/{run_id}?token=s3cret-for-this-test&last_seq=0")
        assert stream.status == 200
        stream.wait_for(lambda: bool(stream.typed()))
        stream.close()
    finally:
        cli.stop()


# ── what a quiet run and a closed tab do to the server ─────────────────────────


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[int, object]]:
    """The app in this process, so its hub can be read, with a short heartbeat."""
    monkeypatch.setattr(sse, "_HEARTBEAT_INTERVAL", 0.3)
    app = create_app(settings=Settings(db=str(tmp_path / "runs.db")))
    port = free_port()
    srv = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    )
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not srv.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    try:
        yield port, app
    finally:
        srv.should_exit = True
        thread.join(15)


def test_a_quiet_run_gets_heartbeats_and_a_closed_tab_is_let_go(
    server: tuple[int, object],
) -> None:
    port, app = server
    hub = app.state.hub  # type: ignore[attr-defined]
    stream = open_stream(port, "/sse/live/quiet-run?last_seq=-1")
    stream.wait_for(lambda: sum(e.comment == "heartbeat" for e in stream.events) >= 2, 10)
    assert "quiet-run" in hub._channels

    stream.close()
    deadline = time.monotonic() + 10
    while "quiet-run" in hub._channels and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "quiet-run" not in hub._channels, "a closed connection kept its subscription"


@pytest.mark.parametrize(
    ("last_seq", "header", "expected"),
    [
        (-1, None, -1),
        (4, None, 4),
        (-1, "7", 7),
        (9, "7", 9),  # never further back than the URL says
        (3, "not-a-number", 3),
        (3, " 5 ", 5),
    ],
)
def test_where_a_connection_resumes(last_seq: int, header: str | None, expected: int) -> None:
    assert sse._resume_after(last_seq, header) == expected
