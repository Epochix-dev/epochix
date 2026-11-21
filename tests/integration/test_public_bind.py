"""A server bound beyond this machine with no token says so — from every command.

`epochix serve --host 0.0.0.0` warned. The server `epochix <log>` and
`epochix --live` start bound `EPOCHIX_HOST` and said nothing: with
`EPOCHIX_HOST=0.0.0.0` a live run listened on every interface, with no token,
and anyone on the network could create and delete runs. `serve` meanwhile
ignored `EPOCHIX_HOST`, and nothing read `EPOCHIX_PORT` at all, while the docs
gave both as the server's address.

Both commands now take the address from the same place — the flag, then the
setting, then 127.0.0.1:7860 — and run the same check. These drive the real CLI.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

WARNING = "without EPOCHIX_AUTH_TOKEN"
LOG = Path(__file__).parents[1] / "fixtures" / "logs" / "keras_50ep.log"
LIVE_LINES = "".join(
    f"Epoch {e}/3 train_loss={1.6 - e * 0.2:.3f} val_accuracy={0.5 + e * 0.06:.3f}\n"
    for e in range(1, 4)
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"EPOCHIX_HOST", "EPOCHIX_PORT", "EPOCHIX_AUTH_TOKEN"}
    }
    return {**env, "EPOCHIX_DB": str(tmp_path / "runs.db"), "PYTHONIOENCODING": "utf-8", **extra}


def _run(
    tmp_path: Path, args: list[str], env: dict[str, str], stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the real CLI to the end: a --live run ends when its stdin closes."""
    return subprocess.run(  # noqa: S603 — this package's own CLI
        [sys.executable, "-m", "epochix.cli", *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=env,
        timeout=120,
        check=False,
    )


def _serve(tmp_path: Path, args: list[str], env: dict[str, str], port: int) -> str:
    """Start `epochix serve`, wait until it answers on *port*, stop it, return its output."""
    return _answer_then_stop(tmp_path, ["-m", "epochix.cli", "serve", *args], env, port)


def _answer_then_stop(tmp_path: Path, argv: list[str], env: dict[str, str], port: int) -> str:
    """Run `python <argv>`, wait until it answers on *port*, stop it, return its output."""
    import urllib.request

    proc = subprocess.Popen(  # noqa: S603 — this package's own code
        [sys.executable, *argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=tmp_path,
        env=env,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(  # noqa: S310
                    f"http://127.0.0.1:{port}/api/health", timeout=2
                ) as resp:
                    assert resp.status == 200
                    break
            except OSError:
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError(f"{argv} did not answer on {port}") from None
                time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            out = proc.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.communicate(timeout=5)[0]
    return out


# ── the server `epochix <log>` and `epochix --live` start ──────────────────────


def test_a_live_run_bound_publicly_without_a_token_says_so(tmp_path: Path) -> None:
    port = free_port()
    proc = _run(
        tmp_path,
        ["--live", "--headless", "--port", str(port)],
        _env(tmp_path, EPOCHIX_HOST="0.0.0.0"),  # noqa: S104 — the point
        stdin=LIVE_LINES,
    )
    assert proc.returncode == 0, proc.stderr
    assert WARNING in proc.stderr, proc.stderr
    assert f"0.0.0.0:{port}" in proc.stderr, proc.stderr


def test_a_live_run_with_a_token_or_on_loopback_does_not_warn(tmp_path: Path) -> None:
    for extra in ({"EPOCHIX_HOST": "0.0.0.0", "EPOCHIX_AUTH_TOKEN": "t0k"}, {}):  # noqa: S104
        proc = _run(
            tmp_path,
            ["--live", "--headless", "--port", str(free_port())],
            _env(tmp_path, **extra),
            stdin=LIVE_LINES,
        )
        assert proc.returncode == 0, (extra, proc.stderr)
        assert WARNING not in proc.stdout + proc.stderr, (extra, proc.stderr)


def test_the_warning_goes_to_stderr_so_json_output_still_parses(tmp_path: Path) -> None:
    port = free_port()
    proc = _run(
        tmp_path,
        [str(LOG), "--json"],
        _env(tmp_path, EPOCHIX_HOST="0.0.0.0", EPOCHIX_PORT=str(port)),  # noqa: S104
    )
    assert proc.returncode == 0, proc.stderr
    assert WARNING in proc.stderr, proc.stderr
    # EPOCHIX_PORT chose the port: nothing else said it.
    assert f"0.0.0.0:{port}" in proc.stderr, proc.stderr
    assert json.loads(proc.stdout)["id"]


# ── `epochix serve` ─────────────────────────────────────────────────────────


def test_serve_reads_the_host_and_port_settings(tmp_path: Path) -> None:
    port = free_port()
    out = _serve(
        tmp_path,
        [],
        _env(tmp_path, EPOCHIX_HOST="0.0.0.0", EPOCHIX_PORT=str(port)),  # noqa: S104
        port,
    )
    assert f"http://0.0.0.0:{port}" in out, out
    assert WARNING in out, out


def test_serve_flags_win_over_the_settings(tmp_path: Path) -> None:
    port = free_port()
    out = _serve(
        tmp_path,
        ["--host", "127.0.0.1", "--port", str(port)],
        _env(tmp_path, EPOCHIX_HOST="0.0.0.0", EPOCHIX_PORT=str(free_port())),  # noqa: S104
        port,
    )
    assert f"http://127.0.0.1:{port}" in out, out
    assert WARNING not in out, out


# ── the Python SDK: epochix.serve and epochix.visualize ────────────────────────
#
# Both take the address as an argument and bound it in silence. They warn with
# PublicBindWarning, a UserWarning, so a notebook shows it and a caller who
# means it can filter it.

_SDK_SERVE = """
import sys, epochix
epochix.serve(host=sys.argv[1], port=int(sys.argv[2]), open_browser=False)
"""

_SDK_VISUALIZE = """
import sys, epochix
run = epochix.parse(sys.argv[3], db=sys.argv[4])
epochix.visualize(run, host=sys.argv[1], port=int(sys.argv[2]), db=sys.argv[4])
"""


def _sdk(tmp_path: Path, script: str, host: str, **extra: str) -> str:
    port = free_port()
    argv = ["-c", script, host, str(port), str(LOG), str(tmp_path / "sdk.db")]
    env = _env(tmp_path, EPOCHIX_OPEN_BROWSER="false", **extra)
    return _answer_then_stop(tmp_path, argv, env, port)


def test_the_sdk_serve_bound_publicly_without_a_token_warns(tmp_path: Path) -> None:
    out = _sdk(tmp_path, _SDK_SERVE, "0.0.0.0")  # noqa: S104 — the point
    assert "PublicBindWarning" in out, out
    assert WARNING in out, out


def test_the_sdk_visualize_bound_publicly_without_a_token_warns(tmp_path: Path) -> None:
    out = _sdk(tmp_path, _SDK_VISUALIZE, "0.0.0.0")  # noqa: S104 — the point
    assert "PublicBindWarning" in out, out
    assert WARNING in out, out


def test_the_sdk_with_a_token_or_on_loopback_does_not_warn(tmp_path: Path) -> None:
    for script in (_SDK_SERVE, _SDK_VISUALIZE):
        for host, extra in (("0.0.0.0", {"EPOCHIX_AUTH_TOKEN": "t0k"}), ("127.0.0.1", {})):  # noqa: S104
            out = _sdk(tmp_path, script, host, **extra)
            assert WARNING not in out, (host, extra, out)
