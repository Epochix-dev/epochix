"""Unit tests for the SSH-tail ingester.

These exercise argv construction, target/path parsing, the shlex-quoting that
keeps a malicious remote path from being interpreted by the remote shell, and
the subprocess lifecycle. The subprocess itself is mocked so no real SSH
binary or remote host is required — these tests run anywhere CI does.
"""
from __future__ import annotations

import asyncio

import pytest

from epochix.ingester import make_ingester
from epochix.ingester.ssh import SSHIngester, parse_ssh_target

# ── parse_ssh_target ─────────────────────────────────────────────────────────


def test_parse_ssh_target_with_user() -> None:
    assert parse_ssh_target("kv@trainbox:/workspace/train.log") == (
        "kv@trainbox", "/workspace/train.log",
    )


def test_parse_ssh_target_without_user() -> None:
    assert parse_ssh_target("trainbox:/workspace/train.log") == (
        "trainbox", "/workspace/train.log",
    )


def test_parse_ssh_target_with_relative_path() -> None:
    assert parse_ssh_target("kv@trainbox:runs/train.log") == (
        "kv@trainbox", "runs/train.log",
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
    assert argv[-1] == "tail -F -n +0 /workspace/train.log"


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
    assert remote_cmd == "tail -F -n +0 '/runs/with space/train; rm -rf ~/.log'"


def test_constructor_rejects_empty_path() -> None:
    with pytest.raises(ValueError):
        SSHIngester(run_id="r", target="trainbox", remote_path="")


def test_constructor_rejects_empty_target() -> None:
    with pytest.raises(ValueError):
        SSHIngester(run_id="r", target="", remote_path="/x")


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

    async def readline(self) -> bytes:
        if not self._lines:
            return b""  # EOF
        return self._lines.pop(0)

    async def read(self) -> bytes:
        return b""


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
    monkeypatch: pytest.MonkeyPatch, proc: _FakeProc,
) -> None:
    async def _fake_exec(*_args, **_kwargs) -> _FakeProc:  # noqa: ANN002, ANN003
        return proc

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", _fake_exec,
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
        run_id="r", target="trainbox", remote_path="/runs/train.log",
    )

    async def _drain() -> None:
        async for _ in ing.lines():
            pass

    with pytest.raises(ConnectionError) as exc:
        asyncio.run(_drain())
    assert "trainbox" in str(exc.value)
