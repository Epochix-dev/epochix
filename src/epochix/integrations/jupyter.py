"""Jupyter / Colab cell magic integration.

Registers the ``%epochix`` and ``%%epochix`` magics.

Usage in a notebook cell::

    %load_ext epochix

    # Parse a finished log file and render inline:
    %epochix train.log

    # Live mode — runs the next cell's output through epochix:
    %%epochix --live
    !python train.py

The magic renders an ``<iframe>`` pointing at the local epochix server.
If the server is not running, it starts one in a background thread.

``IPython`` is required; this module is a no-op when imported outside
a notebook environment.
"""

from __future__ import annotations

import argparse
import threading
from pathlib import Path
from typing import Any


def load_ipython_extension(ipython: Any) -> None:  # noqa: ANN401
    """Called by ``%load_ext epochix``."""
    ipython.register_magic_function(_line_magic, magic_kind="line", magic_name="epochix")
    ipython.register_magic_function(_cell_magic, magic_kind="cell", magic_name="epochix")


def unload_ipython_extension(ipython: Any) -> None:  # noqa: ANN401
    """Called by ``%unload_ext epochix``."""


# ── magic implementations ─────────────────────────────────────────────────────


def _line_magic(line: str) -> None:
    """``%epochix [OPTIONS] [LOG_FILE]``

    Options
    -------
    --task TASK       Force task type
    --port PORT       Dashboard port (default 7860)
    --height HEIGHT   iframe height in px (default 600)
    --no-browser      Don't open browser window
    """

    try:
        from IPython.display import IFrame, display  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        print("[epochix] IPython is required for the magic.")
        return

    args, rest = _parse_magic_args(line.split())
    log_path = Path(rest[0]) if rest else None

    port = args.port
    height = args.height

    _ensure_server(port=port)

    if log_path and log_path.exists():
        run = _parse_and_register(log_path, task=args.task, port=port)
        url = f"http://127.0.0.1:{port}/v/{run.id}"
    else:
        url = f"http://127.0.0.1:{port}"

    display(IFrame(src=url, width="100%", height=height))


def _cell_magic(line: str, cell: str) -> None:
    """``%%epochix [OPTIONS]``

    Runs the cell body and pipes its stdout through epochix in live mode.
    The cell body is executed via IPython's ``%%script`` internally.
    """
    import subprocess
    import sys

    try:
        from IPython.display import IFrame, display  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        print("[epochix] IPython is required for the magic.")
        return

    args, _ = _parse_magic_args(line.split())
    port = args.port
    height = args.height

    _ensure_server(port=port)

    # Write cell to a temp script and run it, piping stdout to epochix
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(cell)
        tmp = f.name

    try:
        from epochix.sdk.live_reporter import LiveReporter

        run_id_holder: list[str] = []

        def _run_cell() -> None:
            reporter = LiveReporter(
                task=args.task,
                port=port,
                open_browser=False,
                locale="en",
            )
            run_id_holder.append(reporter._run_id)  # noqa: SLF001
            proc = subprocess.Popen(
                [sys.executable, tmp],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with reporter:
                for out_line in proc.stdout or []:
                    print(out_line, end="")
                    reporter.log(raw=0.0)  # push heartbeat; parser sees stdout

        t = threading.Thread(target=_run_cell, daemon=True)
        t.start()
        t.join(timeout=2)  # wait briefly for run_id

        run_id = run_id_holder[0] if run_id_holder else None
        url = f"http://127.0.0.1:{port}/v/{run_id}" if run_id else f"http://127.0.0.1:{port}"

        try:
            from IPython.display import (  # type: ignore[import-not-found,unused-ignore]
                IFrame,
                display,
            )

            display(IFrame(src=url, width="100%", height=height))
        except ImportError:
            print(f"[epochix] Dashboard: {url}")

    finally:
        os.unlink(tmp)


# ── server management ─────────────────────────────────────────────────────────

_server_lock = threading.Lock()
_server_running: set[int] = set()


def _ensure_server(*, port: int = 7860) -> None:
    """Start the epochix server if not already running on *port*."""
    with _server_lock:
        if port in _server_running:
            return
        _server_running.add(port)

    def _start() -> None:
        import uvicorn

        from epochix.config import get_settings
        from epochix.server.app import create_app

        settings = get_settings()
        _app = create_app(settings=settings)

        uvicorn.run(
            _app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )

    thread = threading.Thread(target=_start, daemon=True, name=f"ms-jupyter-{port}")
    thread.start()

    # Brief wait for server to be ready
    import time
    import urllib.request

    for _ in range(20):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.3)


def _parse_and_register(log_path: Path, *, task: str | None, port: int) -> Any:  # noqa: ANN401
    """Parse *log_path* and register the run with the running server."""
    from epochix.sdk.parse import parse

    return parse(str(log_path), task=task)


# ── argument parsing ──────────────────────────────────────────────────────────


def _parse_magic_args(argv: list[str]) -> tuple[Any, list[str]]:  # noqa: ANN401
    p = _make_parser()
    return p.parse_known_args(argv)


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="%epochix", add_help=False)
    p.add_argument("--task", default=None, help="Force task type")
    p.add_argument("--port", default=7860, type=int, help="Dashboard port")
    p.add_argument("--height", default=600, type=int, help="iframe height px")
    p.add_argument("--no-browser", action="store_true")
    return p
