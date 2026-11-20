"""A real `epochix --live` run, fed line by line, for tests that watch it live.

The CLI starts its own server, reads stdin, and stops the server once stdin
closes and the run is told. Tests write a line, look at what the server sends,
and write the next — the journey a training script piped into epochix takes.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def epoch_line(epoch: int, of: int) -> str:
    return (
        f"Epoch {epoch}/{of} train_loss={1.6 - epoch * 0.2:.3f} "
        f"val_accuracy={0.5 + epoch * 0.06:.3f}"
    )


class LiveCli:
    """``python -m epochix.cli --live --headless`` on a free port."""

    def __init__(self, workdir: Path, *, env: dict[str, str] | None = None) -> None:
        self.port = free_port()
        self.db = workdir / "runs.db"
        self.output: list[str] = []
        self.proc = subprocess.Popen(  # noqa: S603 — this package's own CLI
            [
                sys.executable,
                "-m",
                "epochix.cli",
                "--live",
                "--port",
                str(self.port),
                "--headless",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=workdir,
            env={
                **os.environ,
                "EPOCHIX_DB": str(self.db),
                "PYTHONIOENCODING": "utf-8",
                **(env or {}),
            },
        )
        threading.Thread(target=self._drain, daemon=True).start()
        self._wait_for_server()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _drain(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.output.append(line)

    def _wait_for_server(self) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"epochix --live exited: {''.join(self.output)}")
            if self.get("/api/health")[0] == 200:
                return
            time.sleep(0.1)
        raise RuntimeError("epochix --live did not serve within 30 s")

    def get(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request("GET", path, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8")
        except OSError:
            return 0, ""
        finally:
            conn.close()

    def write(self, *lines: str) -> None:
        assert self.proc.stdin is not None
        for line in lines:
            self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def run_id(self, timeout: float = 30) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, body = self.get("/api/runs")
            if status == 200 and (runs := json.loads(body).get("runs")):
                return str(runs[0]["id"])
            time.sleep(0.1)
        raise AssertionError(f"no run appeared: {''.join(self.output)}")

    def frames(self, run_id: str) -> list[dict[str, object]]:
        status, body = self.get(f"/api/snapshot/{run_id}")
        assert status == 200, body
        frames: list[dict[str, object]] = json.loads(body)["frames"]
        return frames

    def wait_for_frames(self, run_id: str, count: int, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.frames(run_id)) >= count:
                return
            time.sleep(0.1)
        raise AssertionError(f"fewer than {count} frames after {timeout} s")

    def finish(self, timeout: float = 30) -> int:
        """Close stdin, as a training script ending does, and wait for the CLI."""
        assert self.proc.stdin is not None
        if not self.proc.stdin.closed:
            self.proc.stdin.close()
        return self.proc.wait(timeout)

    def stop(self) -> None:
        if self.proc.poll() is None:
            if self.proc.stdin is not None and not self.proc.stdin.closed:
                self.proc.stdin.close()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
