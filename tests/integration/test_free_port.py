"""The free-port check refuses exactly the ports the server could not take.

It bound one IPv4 socket without `SO_REUSEADDR`, everywhere. On Linux and
macOS that bind is refused for about a minute after a server on the port
stops, while its old connections sit in TIME_WAIT, though uvicorn (which sets
`SO_REUSEADDR` there, as asyncio does) would have started: stopping
`epochix serve` and starting it again was told "Port 7860 is already in use".
An IPv6 host (`--host ::1`) and an address this machine does not have were
both reported as a port in use too.
"""

from __future__ import annotations

import asyncio
import errno
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
import typer

from epochix.cli import _require_free_port

ROOT = Path(__file__).resolve().parents[2]


def _left_in_time_wait() -> int:
    """A port whose server has stopped, with a closed connection in TIME_WAIT.

    The server closes the connection first, so the TIME_WAIT is on the
    server's own address: what a stopped `epochix serve` leaves behind.
    """

    async def serve_one() -> int:
        async def hang_up(_r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
            w.close()
            await w.wait_closed()

        server = await asyncio.start_server(hang_up, "127.0.0.1", 0)
        port = int(server.sockets[0].getsockname()[1])
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        await reader.read()
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()
        return port

    return asyncio.run(serve_one())


def _plain_bind_refused(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as plain:
        try:
            plain.bind((host, port))
        except OSError as exc:
            return exc.errno == errno.EADDRINUSE
    return False


def _stderr_of(capsys: pytest.CaptureFixture[str], host: str, port: int) -> str:
    with pytest.raises(typer.Exit) as stopped:
        _require_free_port(host, port)
    assert stopped.value.exit_code == 1
    return capsys.readouterr().err


@pytest.mark.skipif(os.name != "posix", reason="TIME_WAIT blocks a plain bind only on POSIX")
def test_a_port_left_in_time_wait_is_free_and_the_server_starts_on_it(tmp_path: Path) -> None:
    port = _left_in_time_wait()
    # Without this the test proves nothing: the case is a bind that a plain
    # socket is refused and the server's own is not.
    assert _plain_bind_refused("127.0.0.1", port), "the setup left nothing in TIME_WAIT"

    _require_free_port("127.0.0.1", port)

    server = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "epochix", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(tmp_path),
        env={
            **os.environ,
            "EPOCHIX_DB": str(tmp_path / "runs.db"),
            "PYTHONPATH": str(ROOT / "src"),
        },
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            if server.poll() is not None:
                out = server.stdout.read() if server.stdout else ""
                pytest.fail(f"epochix serve exited {server.returncode}:\n{out}")
            try:
                url = f"http://127.0.0.1:{port}/api/health"
                with urllib.request.urlopen(url, timeout=2) as answer:  # noqa: S310
                    assert answer.status == 200
                    break
            except OSError:
                assert time.monotonic() < deadline, "epochix serve never answered"
                time.sleep(0.2)
    finally:
        server.terminate()
        server.wait(timeout=30)


def test_a_port_a_server_listens_on_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    """As the server binds, on every platform: an epochix already running."""

    async def check() -> str:
        held = await asyncio.start_server(lambda _r, _w: None, "127.0.0.1", 0)
        try:
            return _stderr_of(capsys, "127.0.0.1", int(held.sockets[0].getsockname()[1]))
        finally:
            held.close()
            await held.wait_closed()

    err = asyncio.run(check())
    assert "already in use" in err, err
    assert "--port" in err, err


def _ipv6_loopback() -> bool:
    if not socket.has_ipv6:
        return False
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
            probe.bind(("::1", 0))
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _ipv6_loopback(), reason="no IPv6 loopback here")
def test_an_ipv6_host_is_probed_as_ipv6(capsys: pytest.CaptureFixture[str]) -> None:
    """An IPv4 socket cannot bind ::1, so a free port there was called busy."""
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as spare:
        spare.bind(("::1", 0))
        free = int(spare.getsockname()[1])
    _require_free_port("::1", free)

    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as held:
        held.bind(("::1", 0))
        held.listen(1)
        err = _stderr_of(capsys, "::1", int(held.getsockname()[1]))
    assert "already in use" in err, err


def test_an_address_this_machine_lacks_is_not_called_a_busy_port(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # 192.0.2.0/24 is reserved for documentation (RFC 5737): no machine has it.
    err = _stderr_of(capsys, "192.0.2.1", 7860)
    assert "already in use" not in err, err
    assert "Cannot listen on 192.0.2.1 port 7860" in err, err
    assert "127.0.0.1" in err, err
