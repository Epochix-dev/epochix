"""Unit tests for the SSH-tail ingester.

These exercise argv construction, target/path parsing, the shlex-quoting that
keeps a malicious remote path from being interpreted by the remote shell, and
the subprocess lifecycle. The subprocess itself is mocked so no real SSH
binary or remote host is required — these tests run anywhere CI does.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from epochix.ingester import BaseIngester, make_ingester
from epochix.ingester.file_batch import FileBatchIngester
from epochix.ingester.ssh import SSHIngester, parse_ssh_target
from epochix.models import RawLogLine
from epochix.pipeline import _line_states, run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

# ── parse_ssh_target ─────────────────────────────────────────────────────────


def test_parse_ssh_target_with_user() -> None:
    assert parse_ssh_target("kv@trainbox:/workspace/train.log") == (
        "kv@trainbox",
        "/workspace/train.log",
    )


def test_parse_ssh_target_without_user() -> None:
    assert parse_ssh_target("trainbox:/workspace/train.log") == (
        "trainbox",
        "/workspace/train.log",
    )


def test_parse_ssh_target_with_relative_path() -> None:
    assert parse_ssh_target("kv@trainbox:runs/train.log") == (
        "kv@trainbox",
        "runs/train.log",
    )


@pytest.mark.parametrize("bad", ["no-colon", "host:", ":/path", ""])
def test_parse_ssh_target_rejects_malformed(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_ssh_target(bad)


# ── build_argv ───────────────────────────────────────────────────────────────


def test_build_argv_minimal() -> None:
    ing = SSHIngester(
        run_id="r",
        target="kv@trainbox",
        remote_path="/workspace/train.log",
    )
    argv = ing.build_argv()
    # core ssh hardening flags are always present
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in argv
    assert "ServerAliveInterval=30" in argv
    assert "ServerAliveCountMax=4" in argv
    assert argv[-2] == "kv@trainbox"
    assert argv[-1] == "tail -F -n +0 -- /workspace/train.log"


def test_build_argv_with_port_identity_opts() -> None:
    ing = SSHIngester(
        run_id="r",
        target="kv@trainbox",
        remote_path="/workspace/train.log",
        port=2222,
        identity="/keys/id_ed25519",
        extra_opts=("ProxyJump=bastion", "Compression=yes"),
    )
    argv = ing.build_argv()
    # -p, -i, and the extra -o entries must all appear
    assert "-p" in argv and argv[argv.index("-p") + 1] == "2222"
    assert "-i" in argv and argv[argv.index("-i") + 1] == "/keys/id_ed25519"
    assert argv.count("ProxyJump=bastion") == 1
    assert argv.count("Compression=yes") == 1


def test_build_argv_quotes_paths_with_spaces() -> None:
    """A remote path with spaces / shell metacharacters must be shell-quoted so
    the remote shell can't interpret it as multiple words or a command."""
    ing = SSHIngester(
        run_id="r",
        target="trainbox",
        remote_path="/runs/with space/train; rm -rf ~/.log",
    )
    argv = ing.build_argv()
    remote_cmd = argv[-1]
    # The whole path becomes one shell-quoted token, so semicolons / spaces
    # inside it can NOT execute on the remote.
    assert remote_cmd == "tail -F -n +0 -- '/runs/with space/train; rm -rf ~/.log'"


def test_constructor_rejects_empty_path() -> None:
    with pytest.raises(ValueError):
        SSHIngester(run_id="r", target="trainbox", remote_path="")


def test_constructor_rejects_empty_target() -> None:
    with pytest.raises(ValueError):
        SSHIngester(run_id="r", target="", remote_path="/x")


# ── argument-injection hardening ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "evil",
    [
        "-oProxyCommand=touch /tmp/pwned",  # ssh option → arbitrary local exec
        "-i/tmp/evilkey",
        "-Flocalfile",
        "-",
    ],
)
def test_target_starting_with_dash_is_rejected(evil: str) -> None:
    """A target beginning with '-' would be parsed by ssh as an option (e.g.
    ProxyCommand → RCE). It must be rejected, not passed through."""
    with pytest.raises(ValueError, match="argument injection"):
        SSHIngester(run_id="r", target=evil, remote_path="/log")


def test_parse_ssh_target_rejects_dash_host() -> None:
    with pytest.raises(ValueError, match="argument injection"):
        parse_ssh_target("-oProxyCommand=evil:/log")


def test_remote_path_starting_with_dash_is_not_a_tail_flag() -> None:
    """A path beginning with '-' must not be interpreted by ``tail`` as an
    option — the ``--`` terminator keeps it a path."""
    ing = SSHIngester(run_id="r", target="host", remote_path="--version")
    assert ing.build_argv()[-1] == "tail -F -n +0 -- --version"


# ── factory wiring ───────────────────────────────────────────────────────────


def test_factory_returns_ssh_ingester() -> None:
    ing = make_ingester(
        source="ssh",
        run_id="r",
        path="/workspace/train.log",
        ssh_target="kv@trainbox",
        ssh_port=22,
        ssh_identity="/k",
        ssh_opts=("ProxyJump=bastion",),
    )
    assert isinstance(ing, SSHIngester)


def test_factory_requires_target_for_ssh() -> None:
    with pytest.raises(ValueError):
        make_ingester(source="ssh", run_id="r", path="/x")


# ── subprocess lifecycle (mocked) ────────────────────────────────────────────


class _FakeReader:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def read(self, _n: int = -1) -> bytes:
        if not self._lines:
            return b""  # EOF
        return self._lines.pop(0)


class _FakeProc:
    """Minimal stand-in for asyncio.subprocess.Process."""

    def __init__(self, lines: list[bytes], rc: int = 0) -> None:
        self.stdout = _FakeReader(lines)
        self.stderr = _FakeReader([])
        self._rc = rc
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        self.returncode = self._rc
        return self._rc

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = self._rc

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _install_fake_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    proc: _FakeProc,
) -> None:
    async def _fake_exec(*_args, **_kwargs) -> _FakeProc:  # noqa: ANN002, ANN003
        return proc

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        _fake_exec,
    )


def test_ingester_yields_lines_then_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _FakeProc(
        lines=[b"Epoch 1/10 loss=2.3\n", b"Epoch 2/10 loss=1.8\n"],
        rc=0,
    )
    _install_fake_subprocess(monkeypatch, proc)

    ing = SSHIngester(
        run_id="r",
        target="kv@trainbox",
        remote_path="/runs/train.log",
    )

    async def _collect() -> list[str]:
        out: list[str] = []
        async for line in ing.lines():
            out.append(line.text)
        return out

    texts = asyncio.run(_collect())
    assert texts == ["Epoch 1/10 loss=2.3", "Epoch 2/10 loss=1.8"]


def test_ingester_raises_on_nonzero_ssh_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    # No stdout lines, then ssh exits non-zero — must surface a ConnectionError.
    proc = _FakeProc(lines=[], rc=255)

    class _ErrReader(_FakeReader):
        async def read(self) -> bytes:
            return b"ssh: Could not resolve hostname trainbox"

    proc.stderr = _ErrReader([])
    _install_fake_subprocess(monkeypatch, proc)

    ing = SSHIngester(
        run_id="r",
        target="trainbox",
        remote_path="/runs/train.log",
    )

    async def _drain() -> None:
        async for _ in ing.lines():
            pass

    with pytest.raises(ConnectionError) as exc:
        asyncio.run(_drain())
    assert "trainbox" in str(exc.value)


# ── the read loop, on a real pipe ────────────────────────────────────────────
#
# No ssh and no host: a child process stands in for `ssh host 'tail -F …'` and
# writes what the test hands it, when the test hands it. The ingester spawns
# it with asyncio's own create_subprocess_exec and reads its real stdout pipe.

_CR = chr(13)
_STEP_BAR = "Steps:   {n}%|#         | {n}/100 [00:26<00:43,  1.85it/s, loss=0.{n}, lr=0.0001]"
_EPOCH_BAR = "Epoch 1/12: {n}%|#   | {n}/100 [00:00<00:00, loss=2.{n}]"

# Writes <dir>/0, <dir>/1, … to stdout as each appears, and exits on <dir>/end.
_REMOTE = """
import os, sys, time
folder, n, deadline = sys.argv[1], 0, time.time() + 60
while time.time() < deadline:
    piece = os.path.join(folder, str(n))
    if os.path.exists(piece):
        with open(piece, "rb") as fh:
            sys.stdout.buffer.write(fh.read())
        sys.stdout.buffer.flush()
        n += 1
    elif os.path.exists(os.path.join(folder, "end")):
        break
    else:
        time.sleep(0.01)
"""


class _Remote:
    """The far end of the connection: says what it is told to, then hangs up."""

    def __init__(self, folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._folder = folder
        self._said = 0
        self.ingester = SSHIngester(run_id="r", target="kv@trainbox", remote_path="/runs/lora.log")
        monkeypatch.setattr(
            self.ingester,
            "build_argv",
            lambda: [sys.executable, "-c", _REMOTE, str(folder)],
        )

    def say(self, data: bytes) -> None:
        # Written under another name first: the child must not read half of it.
        part = self._folder / "part"
        part.write_bytes(data)
        part.rename(self._folder / str(self._said))
        self._said += 1

    def hang_up(self) -> None:
        (self._folder / "end").touch()


@pytest.fixture
def remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Remote]:
    far_end = _Remote(tmp_path, monkeypatch)
    try:
        yield far_end
    finally:
        far_end.hang_up()


async def _texts(gen: AsyncIterator[RawLogLine]) -> list[str]:
    return [line.text async for line in gen]


async def test_ssh_hands_on_a_step_bar_before_its_line_ends(remote: _Remote) -> None:
    """A LoRA run tailed over ssh showed nothing until a checkpoint ended the
    bar's line: readline() was waiting for a newline."""
    drawn = [_STEP_BAR.format(n=n) for n in (1, 2, 3)]
    remote.say((_CR + _CR.join(drawn)).encode())
    gen = remote.ingester.lines()
    try:
        line = await asyncio.wait_for(gen.__anext__(), timeout=10.0)
        assert line.source == "ssh"
        # The two finished redraws; the third may still be half written.
        assert _line_states(line.text) == drawn[:2]
        # Its end arrives with the next redraw.
        remote.say((_CR + _STEP_BAR.format(n=4)).encode())
        line = await asyncio.wait_for(gen.__anext__(), timeout=10.0)
        assert _line_states(line.text) == [drawn[2]]
        # And the connection's end finishes the one still being drawn.
        remote.hang_up()
        assert await asyncio.wait_for(_texts(gen), timeout=10.0) == [_STEP_BAR.format(n=4)]
    finally:
        await gen.aclose()


async def test_ssh_keeps_an_epoch_bar_until_its_line_ends(remote: _Remote) -> None:
    """Every other bar is read in its final state, so it waits for its newline."""
    drawn = [_EPOCH_BAR.format(n=n) for n in (1, 2, 3)]
    remote.say((_CR + _CR.join(drawn)).encode())
    gen = remote.ingester.lines()
    first = asyncio.ensure_future(gen.__anext__())
    try:
        done, _ = await asyncio.wait({first}, timeout=1.0)
        assert not done, "a redraw was handed on before the bar's line ended"
        remote.say(b"\nafter the bar\n")
        assert _line_states((await asyncio.wait_for(first, timeout=10.0)).text) == [drawn[2]]
        assert (await asyncio.wait_for(gen.__anext__(), timeout=10.0)).text == "after the bar"
    finally:
        first.cancel()
        await gen.aclose()


async def test_ssh_reads_a_bar_line_longer_than_the_stream_limit(remote: _Remote) -> None:
    """readline() raised ValueError once 64 KiB had arrived with no newline —
    a minute or two of a tqdm bar — and the tail ended there."""
    redraws = [_EPOCH_BAR.format(n=n % 100) for n in range(4000)]
    whole = (_CR + _CR.join(redraws) + "\n").encode()
    assert len(whole) > 3 * 65536
    remote.say(whole)
    remote.hang_up()
    texts = await asyncio.wait_for(_texts(remote.ingester.lines()), timeout=20.0)
    assert len(texts) == 1
    assert texts[0].rsplit(_CR, 1)[-1] == redraws[-1]


async def test_ssh_tells_the_recorded_lora_run_as_its_file_is_told(remote: _Remote) -> None:
    """The whole journey: the recorded run through the pipe, the pipeline and
    the store, arriving in pieces that cut its redraws in two."""
    log = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "logs"
    path = log / "diffusers_lora_real.log"
    recorded = path.read_bytes()
    assert _CR.encode() in recorded

    async def told(ingester: BaseIngester, run_id: str) -> list[tuple[str, float | None, float]]:
        store = RunStore(":memory:")
        await run_pipeline(ingester=ingester, run_id=run_id, store=store, hub=Hub())
        return [(e.canonical_key, e.epoch, e.value) for e in store.get_metric_events(run_id)]

    from_file = await told(FileBatchIngester("f", str(path)), "f")
    assert len(from_file) >= 40

    for at in range(0, len(recorded), 7000):
        remote.say(recorded[at : at + 7000])
    remote.hang_up()
    assert await asyncio.wait_for(told(remote.ingester, "p"), timeout=60.0) == from_file
