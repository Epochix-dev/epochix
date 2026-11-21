"""Jupyter / Colab magics: ``%epochix`` and ``%%epochix``.

Usage in a notebook::

    %load_ext epochix

    # Tell the story of a finished log, inline:
    %epochix train.log

    # Run a cell and tell its output live, as it prints:
    %%epochix --live
    !python train.py

Both render an ``<iframe>`` on a dashboard server the kernel starts once per
port and keeps for as long as it runs (``%unload_ext epochix`` stops it).
They share it, so ``%epochix train.log`` and a later ``%%epochix --live`` on
the default port work together; each used to start its own server there, and
the second died binding it.

A ``%%epochix`` cell is run as a separate process, not in the notebook's
namespace: either Python (every line), or ``!`` shell commands (every line),
with the notebook's ``{variables}`` expanded in them as IPython does.

``IPython`` is required; importing this module outside a notebook is harmless.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from epochix.server.hub import Hub
    from epochix.store.sqlite_store import RunStore

_SAY = "[epochix]"


def load_ipython_extension(ipython: Any) -> None:  # noqa: ANN401
    """Called by ``%load_ext epochix``."""
    ipython.register_magic_function(_line_magic, magic_kind="line", magic_name="epochix")
    ipython.register_magic_function(_cell_magic, magic_kind="cell", magic_name="epochix")


def unload_ipython_extension(ipython: Any) -> None:  # noqa: ANN401, ARG001
    """Called by ``%unload_ext epochix``: stop the dashboard servers it started."""
    with _servers_lock:
        servers = list(_servers.values())
        _servers.clear()
    for srv in servers:
        srv.stop()


# ── magic implementations ─────────────────────────────────────────────────────


def _line_magic(line: str) -> None:
    """``%epochix [--port PORT] [--height PX] [--task TASK] [LOG_FILE]``

    With a log file, parse it and show its story; without one, show the
    dashboard's list of runs.
    """
    try:
        from IPython.display import IFrame, display  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        print(f"{_SAY} IPython is required for the magic.")
        return

    try:
        args = _parse_magic_args(line, cell=False)
        task = _task(args.task)
    except (_MagicArgError, ValueError) as exc:
        print(f"{_SAY} {exc}")
        return

    log_path = Path(args.log) if args.log else None
    # A typo used to show the dashboard's home page, saying nothing.
    if log_path is not None and not log_path.is_file():
        print(f"{_SAY} No such file: {log_path}")
        return

    srv = _ensure_server(port=args.port)
    if srv is None:
        return

    url = srv.url
    if log_path is not None:
        run = _parse_and_register(log_path, task=task, db=srv.db)
        url = f"{srv.url}/v/{run.id}"

    display(IFrame(src=url, width="100%", height=args.height))


def _cell_magic(line: str, cell: str) -> None:
    """``%%epochix [--live] [--port PORT] [--height PX] [--task TASK]``

    Runs the cell — Python, or ``!`` shell commands — in a separate process,
    shows the dashboard at once, and tells the output live as it is printed.
    The cell runs until the process ends; interrupting the kernel stops it.
    """
    try:
        from IPython.display import IFrame, display  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        print(f"{_SAY} IPython is required for the magic.")
        return

    try:
        args = _parse_magic_args(line, cell=True)
        task = _task(args.task)
        commands = _cell_commands(cell)
    except (_MagicArgError, ValueError) as exc:
        print(f"{_SAY} {exc}")
        return
    if not commands:
        print(f"{_SAY} The cell is empty: nothing to run.")
        return

    srv = _ensure_server(port=args.port)
    if srv is None:
        return

    from ulid import ULID

    from epochix.ingester.sdk_receiver import SDKReceiver
    from epochix.pipeline import run_pipeline

    run_id = str(ULID())
    receiver = SDKReceiver(run_id=run_id)
    told = srv.submit(
        run_pipeline(
            ingester=receiver,
            run_id=run_id,
            store=srv.store,
            hub=srv.hub,
            run_name="notebook cell",
            task=task,
        )
    )
    display(IFrame(src=f"{srv.url}/v/{run_id}", width="100%", height=args.height))

    def relay(text: str) -> None:
        # The receiver's queue belongs to the server's loop; put lines on it
        # from there, not from this thread.
        srv.loop.call_soon_threadsafe(receiver.push_line, text)

    failed: Exception | None = None
    try:
        code = _run_commands(commands, relay)
    finally:
        # Also on an interrupt: end the stream, so the run is finished and
        # told from what was printed before it.
        srv.loop.call_soon_threadsafe(receiver.close)
        try:
            told.result(timeout=120)
        except Exception as exc:  # noqa: BLE001 — said below; the output already stands
            failed = exc
    if failed is not None:
        print(f"{_SAY} The run could not be told: {failed}")
        return

    if code:
        print(f"{_SAY} The cell exited with code {code}.")
    if not srv.call(_frame_count(srv.store, run_id)):
        print(
            f"{_SAY} Nothing in the cell's output was read as a training metric, "
            "so there is no story to tell. Print one line per epoch, e.g. "
            "Epoch 3/10 train_loss=0.42 val_accuracy=0.88"
        )


async def _frame_count(store: RunStore, run_id: str) -> int:
    return len(store.get_story_frames(run_id))


# ── running the cell ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Command:
    argv: list[str] | str
    via_shell: bool
    script: Path | None = None


def _cell_commands(cell: str) -> list[_Command]:
    """What the cell runs: one Python script, or its ``!`` shell commands.

    The quickstart's own example is a ``!python train.py`` cell, and the body
    was written to a .py file and run by Python — a SyntaxError, and a run
    with nothing in it.
    """
    lines = [ln for ln in cell.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return []
    bang = [ln.lstrip().startswith("!") for ln in lines]
    if all(bang):
        shell = _ipython()
        out = []
        for ln in lines:
            cmd = ln.lstrip()[1:].strip()
            if shell is not None:
                cmd = shell.var_expand(cmd)
            out.append(_Command(argv=cmd, via_shell=True))
        return out
    if any(bang):
        raise ValueError(
            "A %%epochix cell runs either Python or ! shell commands, not both: "
            "it runs as its own process, where IPython's ! is not Python."
        )
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8", prefix="epochix_cell_"
    ) as f:
        f.write(cell)
    script = Path(f.name)
    return [_Command(argv=[sys.executable, str(script)], via_shell=False, script=script)]


def _run_commands(commands: list[_Command], relay: Any) -> int:  # noqa: ANN401
    """Run each command in turn, echoing and relaying its output; stop at a failure."""
    # Unbuffered: a Python child writing to a pipe buffers its prints, and the
    # live dashboard then saw the whole run at once, when it ended.
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    code = 0
    try:
        for cmd in commands:
            proc = subprocess.Popen(  # noqa: S603 — the user's own cell
                cmd.argv,
                # `!` lines are shell commands by definition: the shell is the feature.
                shell=cmd.via_shell,  # noqa: S602  # nosec B602
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            try:
                for out_line in proc.stdout or []:
                    print(out_line, end="")
                    relay(out_line.rstrip("\r\n"))
                code = proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                proc.wait()
                print(f"\n{_SAY} Stopped.")
                raise
            if code != 0:
                break
    finally:
        for cmd in commands:
            if cmd.script is not None:
                cmd.script.unlink(missing_ok=True)
    return code


def _ipython() -> Any:  # noqa: ANN401
    try:
        from IPython import get_ipython  # type: ignore[import-not-found,attr-defined,unused-ignore]
    except ImportError:
        return None
    return get_ipython()


# ── server management ─────────────────────────────────────────────────────────


@dataclass
class _Server:
    """A dashboard server on its own event loop, for the life of the kernel."""

    port: int
    db: str
    loop: asyncio.AbstractEventLoop
    store: RunStore
    hub: Hub
    server: Any
    thread: threading.Thread

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Any:  # noqa: ANN401
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, coro: Coroutine[Any, Any, Any]) -> Any:  # noqa: ANN401
        """Run *coro* on the server's loop — where its store lives — and wait."""
        return self.submit(coro).result(timeout=30)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


_servers_lock = threading.Lock()
_servers: dict[int, _Server] = {}


def _ensure_server(*, port: int = 7860) -> _Server | None:
    """The kernel's server on *port*, started on first use; None if it cannot be."""
    with _servers_lock:
        srv = _servers.get(port)
        if srv is not None and srv.thread.is_alive():
            return srv
        if not _port_is_free(port):
            # Showing the page anyway showed whatever listened there — another
            # epochix with another database, or not epochix at all.
            print(
                f"{_SAY} Port {port} is already in use by another program. "
                f"Choose another with --port, e.g. --port {port + 1}"
            )
            return None
        srv = _start_server(port)
        if srv is not None:
            _servers[port] = srv
        return srv


def _port_is_free(port: int) -> bool:
    """False only when something is listening on *port*."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        # On POSIX a port the stopped server answered on lingers in TIME_WAIT,
        # and a plain bind fails there though nothing listens; SO_REUSEADDR
        # still fails on a listener. On Windows it would take a listener's port
        # over, and a plain bind is already the right test.
        if os.name != "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _start_server(port: int) -> _Server | None:
    import uvicorn

    from epochix.config import get_settings
    from epochix.server.app import create_app
    from epochix.server.hub import Hub
    from epochix.store.sqlite_store import RunStore

    settings = get_settings()
    store = RunStore(db_path=settings.db)
    hub = Hub()
    app = create_app(settings=settings)
    app.state.store = store
    app.state.hub = hub
    app.state.engine_map = {}
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="off")
    )
    loop = asyncio.new_event_loop()

    def _main() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        except SystemExit:  # uvicorn's answer to a failed bind
            pass
        finally:
            loop.close()

    thread = threading.Thread(target=_main, daemon=True, name=f"epochix-jupyter-{port}")
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        print(f"{_SAY} The dashboard server did not start on port {port}.")
        server.should_exit = True
        return None
    return _Server(
        port=port,
        db=settings.db,
        loop=loop,
        store=store,
        hub=hub,
        server=server,
        thread=thread,
    )


def _parse_and_register(log_path: Path, *, task: Any, db: str) -> Any:  # noqa: ANN401
    """Parse *log_path* into the database the server reads, and return the run.

    parse() defaults to db=":memory:", so without an explicit db the run was
    thrown away and the iframe pointed at a run the server had never heard of.
    """
    from epochix.sdk.parse import parse

    return parse(str(log_path), task=task, db=db, run_name=log_path.name)


# ── argument parsing ──────────────────────────────────────────────────────────


class _MagicArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:  # noqa: ANN401
        # argparse's own answer is sys.exit(2): a SystemExit in the notebook.
        raise _MagicArgError(f"{message}. Usage: {self.format_usage().strip()}")


def _parse_magic_args(line: str, *, cell: bool) -> argparse.Namespace:
    # POSIX quoting would eat a Windows path's backslashes.
    posix = os.name != "nt"
    try:
        argv = [t.strip('"') if not posix else t for t in shlex.split(line, posix=posix)]
    except ValueError as exc:
        raise _MagicArgError(str(exc)) from None
    p = _Parser(prog="%%epochix" if cell else "%epochix", add_help=False)
    p.add_argument("--task", default=None)
    p.add_argument("--port", default=7860, type=int)
    p.add_argument("--height", default=600, type=int)
    # Accepted so older notebooks keep working; the magics never open a browser.
    p.add_argument("--no-browser", action="store_true")
    if cell:
        # A %%epochix cell is always live; the flag is what the docs show.
        p.add_argument("--live", action="store_true")
    else:
        p.add_argument("log", nargs="?", default=None)
    return p.parse_args(argv)


def _task(task: str | None) -> Any:  # noqa: ANN401
    if task is None:
        return None
    from epochix.enums import TaskType

    try:
        return TaskType(task)
    except ValueError:
        names = ", ".join(t.value for t in TaskType)
        raise ValueError(f"Unknown task {task!r}. Tasks: {names}.") from None
