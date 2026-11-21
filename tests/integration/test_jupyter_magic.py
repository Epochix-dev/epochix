"""The %epochix Jupyter magics, driven through a REAL IPython shell.

docs/quickstart.md tells people to run `%load_ext epochix`, but for a long time
nothing executed it, and four bugs shipped behind that gap:

* `%load_ext epochix` printed "The epochix module is not an IPython extension"
  and registered no magics at all — IPython looks for load_ipython_extension on
  the module you name, and it only existed on epochix.integrations.jupyter.
* `%epochix <log>` parsed into the default db=":memory:", so the run was thrown
  away and the iframe pointed at a run the server had never heard of.
* `%%epochix --live` pushed a fabricated `raw=0.0` metric per output line and
  never fed the script's real output to the parser.
* `%%epochix --live` also started a second server on the port LiveReporter was
  already binding, so uvicorn failed to start and killed the reporter thread.

Even then the magics themselves were never run (the first coverage measurement,
ROADMAP item 8). Run, they showed:

* the quickstart's own live example, a `!python train.py` cell, was written to
  a .py file and run by Python: a SyntaxError and a run with nothing in it;
* the live dashboard's server stopped the moment the run ended, so the
  notebook's iframe went dead under the finished story;
* `%epochix train.log` and then `%%epochix --live` on the default port — the
  order the quickstart shows them in — killed the live run with SystemExit(3),
  the two again starting a server each on one port;
* a Python cell's prints reached the parser only when it exited (a child
  writing to a pipe buffers them), so "live" was all at once at the end;
* `%epochix tran.log` (a typo) showed the dashboard's home page, saying
  nothing, and an unknown option was read as the log file's name.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from epochix.enums import TaskType
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from collections.abc import Iterator

pytest.importorskip("IPython")

from IPython.core.interactiveshell import InteractiveShell  # noqa: E402
from IPython.utils.capture import capture_output  # noqa: E402


def _log(tmp_path: Path) -> Path:
    path = tmp_path / "train.log"
    path.write_text(
        "".join(
            f"Epoch {e}/6 train_loss={1.6 - e * 0.2:.3f} val_accuracy={0.5 + e * 0.06:.3f}\n"
            for e in range(1, 7)
        ),
        encoding="utf-8",
    )
    return path


def _epochs(n: int, of: int | None = None) -> str:
    """Python that prints *n* epoch lines, as a training script would."""
    total = of or n
    return "".join(
        f"print('Epoch {e}/{total} train_loss={1.6 - e * 0.2:.3f} "
        f"val_accuracy={0.5 + e * 0.06:.3f}')\n"
        for e in range(1, n + 1)
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _get(url: str) -> Any:  # noqa: ANN401
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 — loopback
        return json.loads(resp.read().decode("utf-8"))


def _iframes(cap: Any) -> list[str]:  # noqa: ANN401
    """The src of every iframe the magic displayed."""
    import re

    out = []
    for o in cap.outputs:
        html = o.data.get("text/html", "")
        out += re.findall(r'src="([^"]+)"', html)
    return out


@pytest.fixture
def shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[InteractiveShell]:
    monkeypatch.setenv("EPOCHIX_DB", str(tmp_path / "runs.db"))
    monkeypatch.setenv("EPOCHIX_OPEN_BROWSER", "false")
    sh = InteractiveShell.instance()
    sh.run_line_magic("load_ext", "epochix")
    yield sh
    # Stop the servers this test started; the next one's database differs.
    from epochix.integrations.jupyter import unload_ipython_extension

    unload_ipython_extension(sh)


def _runs(tmp_path: Path) -> list[Any]:
    return RunStore(db_path=str(tmp_path / "runs.db")).list_runs()


# ── loading ──────────────────────────────────────────────────────────────────


def test_load_ext_epochix_registers_the_magics() -> None:
    """`%load_ext epochix` — the exact line in the quickstart — must work."""
    shell = InteractiveShell.instance()
    shell.run_line_magic("load_ext", "epochix")

    assert "epochix" in shell.magics_manager.magics["line"], "%epochix not registered"
    assert "epochix" in shell.magics_manager.magics["cell"], "%%epochix not registered"


def test_unload_stops_the_dashboard(shell: InteractiveShell) -> None:
    port = _free_port()
    with capture_output():
        shell.run_line_magic("epochix", f"--port {port}")
    assert _get(f"http://127.0.0.1:{port}/api/health") == {"status": "ok"}

    from epochix.integrations.jupyter import _port_is_free, unload_ipython_extension

    unload_ipython_extension(shell)
    with pytest.raises(OSError):
        _get(f"http://127.0.0.1:{port}/api/health")
    # Free to use again — on POSIX, despite the TIME_WAIT the request left.
    assert _port_is_free(port)
    with capture_output() as cap:
        shell.run_line_magic("epochix", f"--port {port}")
    assert "already in use" not in cap.stdout
    assert _get(f"http://127.0.0.1:{port}/api/health") == {"status": "ok"}


# ── %epochix ─────────────────────────────────────────────────────────────────


def test_line_magic_shows_the_run_the_server_serves(
    shell: InteractiveShell, tmp_path: Path
) -> None:
    port = _free_port()
    with capture_output() as cap:
        shell.run_line_magic("epochix", f"{_log(tmp_path)} --port {port}")

    [run] = _runs(tmp_path)
    assert run.task_type == TaskType.CLASSIFICATION
    assert run.name == "train.log"
    assert _iframes(cap) == [f"http://127.0.0.1:{port}/v/{run.id}"]
    snap = _get(f"http://127.0.0.1:{port}/api/snapshot/{run.id}")
    assert len(snap["frames"]) == 6


def test_line_magic_reads_a_path_with_a_space(shell: InteractiveShell, tmp_path: Path) -> None:
    spaced = tmp_path / "my runs" / "train.log"
    spaced.parent.mkdir()
    spaced.write_bytes(_log(tmp_path).read_bytes())
    with capture_output() as cap:
        shell.run_line_magic("epochix", f'"{spaced}" --port {_free_port()}')
    [run] = _runs(tmp_path)
    assert _iframes(cap)[0].endswith(f"/v/{run.id}")


def test_line_magic_without_a_log_shows_the_dashboard(shell: InteractiveShell) -> None:
    port = _free_port()
    with capture_output() as cap:
        shell.run_line_magic("epochix", f"--port {port}")
    assert _iframes(cap) == [f"http://127.0.0.1:{port}"]


@pytest.mark.parametrize(
    ("line", "says"),
    [
        ("tran.log", "No such file: tran.log"),
        ("--prot 9000 train.log", "unrecognized arguments: --prot"),
        ("--port nine", "invalid int value: 'nine'"),
        ("--task segmentaton train.log", "Unknown task 'segmentaton'"),
    ],
)
def test_line_magic_says_what_is_wrong_and_shows_nothing(
    shell: InteractiveShell,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    line: str,
    says: str,
) -> None:
    _log(tmp_path)
    monkeypatch.chdir(tmp_path)
    with capture_output() as cap:
        shell.run_line_magic("epochix", line)
    assert says in cap.stdout, cap.stdout
    assert _iframes(cap) == []
    assert _runs(tmp_path) == []


def test_a_port_taken_by_another_program_is_said(shell: InteractiveShell, tmp_path: Path) -> None:
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        with capture_output() as cap:
            shell.run_line_magic("epochix", f"{_log(tmp_path)} --port {port}")
    assert f"Port {port} is already in use" in cap.stdout
    assert _iframes(cap) == []


def test_parse_and_register_writes_to_the_db_it_is_given(tmp_path: Path) -> None:
    """The parsed run has to land in the served DB, or the iframe is empty."""
    from epochix.integrations.jupyter import _parse_and_register

    db = str(tmp_path / "served.db")
    run = _parse_and_register(_log(tmp_path), task=None, db=db)
    [stored] = RunStore(db_path=db).list_runs()
    assert stored.id == run.id


# ── %%epochix ────────────────────────────────────────────────────────────────


def test_a_python_cell_is_told_and_stays_served(shell: InteractiveShell, tmp_path: Path) -> None:
    port = _free_port()
    with capture_output() as cap:
        shell.run_cell_magic("epochix", f"--live --port {port}", _epochs(5))

    [run] = _runs(tmp_path)
    assert run.name == "notebook cell"
    assert run.finished_at is not None
    assert _iframes(cap) == [f"http://127.0.0.1:{port}/v/{run.id}"]
    assert "Epoch 5/5" in cap.stdout, "the cell's own output must still be shown"
    # The run has ended; the page in the notebook must still load.
    time.sleep(1.0)
    snap = _get(f"http://127.0.0.1:{port}/api/snapshot/{run.id}")
    assert len(snap["frames"]) == 5
    events = RunStore(db_path=str(tmp_path / "runs.db")).get_metric_events(run.id)
    accs = sorted(e.value for e in events if e.canonical_key == "val_accuracy")
    assert accs == pytest.approx([0.56, 0.62, 0.68, 0.74, 0.80])


def test_the_quickstarts_shell_cell_runs(shell: InteractiveShell, tmp_path: Path) -> None:
    """`!python train.py`, with the notebook's variables expanded as IPython does."""
    script = tmp_path / "train.py"
    script.write_text(_epochs(3), encoding="utf-8")
    shell.user_ns["py"] = sys.executable
    shell.user_ns["script"] = str(script)

    with capture_output() as cap:
        shell.run_cell_magic("epochix", f"--live --port {_free_port()}", '!"{py}" "{script}"\n')
    assert "SyntaxError" not in cap.stdout, cap.stdout
    [run] = _runs(tmp_path)
    store = RunStore(db_path=str(tmp_path / "runs.db"))
    assert len(store.get_story_frames(run.id)) == 3


def test_the_line_magic_then_a_live_cell_share_the_port(
    shell: InteractiveShell, tmp_path: Path
) -> None:
    """The quickstart's order, on one port: both runs are told and served."""
    port = _free_port()
    with capture_output():
        shell.run_line_magic("epochix", f"{_log(tmp_path)} --port {port}")
    with capture_output() as cap:
        shell.run_cell_magic("epochix", f"--live --port {port}", _epochs(3))
    assert "Traceback" not in cap.stdout + cap.stderr, cap.stdout + cap.stderr

    runs = {r.name: r for r in _runs(tmp_path)}
    assert set(runs) == {"train.log", "notebook cell"}
    for run, frames in ((runs["train.log"], 6), (runs["notebook cell"], 3)):
        assert len(_get(f"http://127.0.0.1:{port}/api/snapshot/{run.id}")["frames"]) == frames


def test_a_cell_is_told_while_it_is_still_running(shell: InteractiveShell, tmp_path: Path) -> None:
    """Plain print(), no flush: the lines must reach the dashboard as printed."""
    go = tmp_path / "go"
    body = (
        "import pathlib, time\n" + _epochs(2, of=3) + f"deadline = time.time() + 60\n"
        f"while not pathlib.Path({str(go)!r}).exists() and time.time() < deadline:\n"
        "    time.sleep(0.05)\n"
        "print('Epoch 3/3 train_loss=1.000 val_accuracy=0.680')\n"
    )
    port = _free_port()
    done = threading.Event()

    def cell() -> None:
        try:
            with capture_output():
                shell.run_cell_magic("epochix", f"--live --port {port}", body)
        finally:
            done.set()

    worker = threading.Thread(target=cell, daemon=True)
    worker.start()
    seen = 0
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and seen < 2:
            runs = _runs(tmp_path) if (tmp_path / "runs.db").exists() else []
            if runs:
                with_frames = RunStore(db_path=str(tmp_path / "runs.db"))
                seen = len(with_frames.get_story_frames(runs[0].id))
            time.sleep(0.1)
        assert not done.is_set(), "the cell ended before it was released"
    finally:
        go.write_text("", encoding="utf-8")
        worker.join(timeout=60)
    assert seen >= 2, "nothing reached the dashboard until the cell ended"
    [run] = _runs(tmp_path)
    assert len(RunStore(db_path=str(tmp_path / "runs.db")).get_story_frames(run.id)) == 3


def test_a_mixed_cell_is_refused_and_nothing_runs(shell: InteractiveShell, tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    body = f"open({str(marker)!r}, 'w').close()\n!echo hello\n"
    with capture_output() as cap:
        shell.run_cell_magic("epochix", f"--live --port {_free_port()}", body)
    assert "either Python or ! shell commands, not both" in cap.stdout
    assert not marker.exists()
    assert _runs(tmp_path) == []
    assert _iframes(cap) == []


def test_a_cell_that_prints_no_metric_says_so(shell: InteractiveShell) -> None:
    with capture_output() as cap:
        shell.run_cell_magic("epochix", f"--port {_free_port()}", "print('hello')\n")
    assert "hello" in cap.stdout
    assert "Nothing in the cell's output was read as a training metric" in cap.stdout


def test_a_failing_cell_says_its_exit_code_and_tells_what_it_printed(
    shell: InteractiveShell, tmp_path: Path
) -> None:
    body = "import sys\n" + _epochs(2, of=5) + "sys.exit(3)\n"
    with capture_output() as cap:
        shell.run_cell_magic("epochix", f"--port {_free_port()}", body)
    assert "The cell exited with code 3." in cap.stdout
    [run] = _runs(tmp_path)
    assert len(RunStore(db_path=str(tmp_path / "runs.db")).get_story_frames(run.id)) == 2


def test_a_cell_option_error_runs_nothing(shell: InteractiveShell, tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    with capture_output() as cap:
        shell.run_cell_magic(
            "epochix", "--live --task nope", f"open({str(marker)!r}, 'w').close()\n"
        )
    assert "Unknown task 'nope'" in cap.stdout
    assert not marker.exists()


def test_an_interrupt_stops_the_cells_process(tmp_path: Path) -> None:
    """The kernel's stop button raises KeyboardInterrupt while output is read."""
    from epochix.integrations.jupyter import _cell_commands, _run_commands

    marker = tmp_path / "survived"
    commands = _cell_commands(
        "import time\n"
        "print('Epoch 1/9 train_loss=1.0 val_accuracy=0.5', flush=True)\n"
        f"time.sleep(30)\nopen({str(marker)!r}, 'w').close()\n"
    )
    script = commands[0].script
    assert script is not None and script.exists()

    def interrupted(_line: str) -> None:
        raise KeyboardInterrupt

    started = time.monotonic()
    with capture_output(), pytest.raises(KeyboardInterrupt):
        _run_commands(commands, interrupted)
    assert time.monotonic() - started < 20, "the process was waited for, not stopped"
    assert not script.exists(), "the cell's temporary script was left behind"
    time.sleep(0.5)
    assert not marker.exists()


# ── LiveReporter, what the SDK relays a subprocess through ───────────────────


def test_log_line_feeds_real_output_to_the_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiveReporter.log_line() parses the line it is given.

    The cell magic used to call log(raw=0.0) per line instead — a fabricated
    heartbeat — so a live cell produced a run with no real metrics in it.
    """
    monkeypatch.setenv("EPOCHIX_DB", str(tmp_path / "runs.db"))

    from epochix.sdk.live_reporter import LiveReporter

    reporter = LiveReporter(task="classification", name="cell", open_browser=False, port=0)
    with reporter:
        for e in range(1, 5):
            reporter.log_line(
                f"Epoch {e}/4 train_loss={2.0 - e * 0.3:.3f} val_accuracy={0.4 + e * 0.09:.3f}"
            )

    store = RunStore(db_path=str(tmp_path / "runs.db"))
    runs = store.list_runs()
    assert len(runs) == 1
    metrics = store.get_metric_events(runs[0].id)
    keys = {m.canonical_key for m in metrics}

    assert "val_accuracy" in keys and "train_loss" in keys, (
        f"the raw lines were not parsed into real metrics: {keys}"
    )
    assert keys != {"custom"}, "only fabricated/heartbeat metrics were stored"
    accs = sorted(m.value for m in metrics if m.canonical_key == "val_accuracy")
    assert accs == pytest.approx([0.49, 0.58, 0.67, 0.76]), accs
