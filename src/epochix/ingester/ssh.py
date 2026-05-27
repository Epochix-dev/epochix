"""SSH-tail ingester: stream a remote training log into the local pipeline.

Spawns ``ssh <target> 'tail -F <quoted-path>'`` as an asyncio subprocess, yields
each line as a :class:`RawLogLine`, and tears the subprocess down cleanly on
generator exit. SSH credentials and host resolution are handled entirely by
the user's ``ssh`` binary (``~/.ssh/config``, agent, keys) — this module never
sees passwords and refuses to prompt for one (``BatchMode=yes``).

Design notes
------------
* ``asyncio.create_subprocess_exec`` uses a list argv on the *local* side, so
  the target / port / identity arguments can't be shell-injected at our layer.
* The *remote* path is interpreted by the remote shell that ssh spawns, so we
  pass it through :func:`shlex.quote` for safety against spaces / metacharacters.
* ``-o BatchMode=yes`` prevents the subprocess from hanging on a password
  prompt when no key is configured — instead it exits with a clear error.
* ``-o ServerAliveInterval=30 -o ServerAliveCountMax=4`` keeps the connection
  alive across long quiet stretches and gives ~2 min of grace before the
  client gives up — typical for training runs that pause between epochs.
* ``tail -F`` (capital F) follows log rotation, ``-n +0`` replays the whole
  file from the start so the dashboard renders the full trajectory, not just
  whatever arrives after we connect.
"""
from __future__ import annotations

import asyncio
import shlex
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone

from epochix.ingester import BaseIngester
from epochix.models import RawLogLine


class SSHIngester(BaseIngester):
    """Stream lines from a remote file over SSH."""

    def __init__(
        self,
        *,
        run_id: str,
        target: str,
        remote_path: str,
        port: int | None = None,
        identity: str | None = None,
        extra_opts: Iterable[str] = (),
    ) -> None:
        if "@" not in target and not target:
            raise ValueError("ssh target must be 'user@host' or 'host'")
        if not remote_path:
            raise ValueError("remote_path is required for SSHIngester")
        self._run_id = run_id
        self._target = target
        self._remote_path = remote_path
        self._port = port
        self._identity = identity
        self._extra_opts: tuple[str, ...] = tuple(extra_opts)
        self._proc: asyncio.subprocess.Process | None = None

    # ── public ────────────────────────────────────────────────────────────

    def build_argv(self) -> list[str]:
        """Return the exact local-side argv used to spawn ssh.

        Public for tests; never call shell on this list.
        """
        argv: list[str] = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=4",
            "-o", "StrictHostKeyChecking=accept-new",
        ]
        if self._port is not None:
            argv += ["-p", str(self._port)]
        if self._identity:
            argv += ["-i", self._identity]
        for opt in self._extra_opts:
            argv += ["-o", opt]
        # Remote command — quoted for the remote shell.
        remote_cmd = f"tail -F -n +0 {shlex.quote(self._remote_path)}"
        argv += [self._target, remote_cmd]
        return argv

    async def lines(self) -> AsyncIterator[RawLogLine]:
        argv = self.build_argv()
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert self._proc.stdout is not None  # PIPE was requested
        seq = 0
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    # ssh closed stdout — either the connection ended or the
                    # remote tail exited. Surface stderr in the (unlikely)
                    # failure case so the user knows why.
                    code = await self._proc.wait()
                    if code != 0 and self._proc.stderr is not None:
                        err = (await self._proc.stderr.read()).decode(
                            "utf-8", errors="replace"
                        )
                        raise ConnectionError(
                            f"ssh to {self._target} exited {code}: {err.strip()}"
                        )
                    return
                yield RawLogLine(
                    seq=seq,
                    timestamp=datetime.now(tz=timezone.utc),
                    source="ssh",
                    text=raw.decode("utf-8", errors="replace").rstrip("\n"),
                )
                seq += 1
        finally:
            await self._cleanup()

    # ── internal ──────────────────────────────────────────────────────────

    async def _cleanup(self) -> None:
        """Terminate the ssh subprocess if it's still running."""
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


def parse_ssh_target(value: str) -> tuple[str, str]:
    """Split ``user@host:/path/to/log`` into ``("user@host", "/path/to/log")``.

    Accepts ``host:path`` (no user), but rejects values without a ``:`` since
    we always need an explicit remote path — there's no useful default.
    """
    if ":" not in value:
        raise ValueError(
            "Expected '[user@]host:/path/to/log' — missing ':<path>' suffix"
        )
    target, path = value.split(":", 1)
    if not target or not path:
        raise ValueError(
            "Expected '[user@]host:/path/to/log' — empty host or path"
        )
    return target, path
