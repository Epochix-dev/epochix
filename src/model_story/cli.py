"""model-story CLI — one command to rule them all.

Entry point: ``model-story`` (configured in pyproject.toml).

Usage
-----
::

    model-story train.log                   # batch: parse file, open browser
    model-story --live                      # live: read stdin, open browser
    model-story --live --tail train.log     # live: tail file, open browser
    model-story --headless --export html    # CI: export HTML, no browser
    model-story serve --port 7860           # start server only
    model-story list                        # show saved runs
    model-story open <run_id>               # open a saved run in the browser
    model-story export <run_id> --format html|pdf|md|json
    model-story prune --older-than 30d      # delete old runs
    model-story config show
    model-story config set <key> <value>
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import uvicorn

from model_story.config import Settings, get_settings
from model_story.enums import TaskType

if TYPE_CHECKING:
    from model_story.store.sqlite_store import RunStore

app = typer.Typer(
    name="model-story",
    help="Visual storytelling for deep learning training runs.",
    no_args_is_help=True,
    add_completion=False,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(levelname)s  %(name)s  %(message)s",
    )


def _new_run_id() -> str:
    from ulid import ULID

    return str(ULID())


def _open_browser(port: int, run_id: str) -> None:
    url = f"http://127.0.0.1:{port}/v/{run_id}"
    typer.echo(f"  Opening: {url}")
    webbrowser.open(url)


def _task_from_str(task_str: str | None) -> TaskType | None:
    if task_str is None:
        return None
    try:
        return TaskType(task_str)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Unknown task type: {task_str!r}. "
            f"Valid values: {[t.value for t in TaskType]}"
        ) from exc


# ------------------------------------------------------------------
# Main command: model-story [LOG_FILE]
# ------------------------------------------------------------------


@app.command("run")
def cmd_run(  # noqa: C901
    log_file: Path | None = typer.Argument(
        None,
        help="Log file to parse (batch mode).",
        show_default=False,
    ),
    live: bool = typer.Option(False, "--live", help="Read from stdin (live mode)."),
    tail: Path | None = typer.Option(
        None, "--tail", help="Tail a file in live mode.", show_default=False
    ),
    port: int = typer.Option(7860, "--port", "-p", help="Server port."),
    task: str | None = typer.Option(
        None, "--task", "-t", help="Force task type (e.g. biometric).", show_default=False
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM fallback parser."),
    headless: bool = typer.Option(False, "--headless", help="Do not open the browser."),
    export_format: str | None = typer.Option(
        None, "--export", help="Export format (html|pdf|md|json) in headless mode.",
        show_default=False,
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Run name.", show_default=False),
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
) -> None:
    """Parse a training log and visualize it in the browser (the default action)."""
    _configure_logging(log_level)
    settings = get_settings()
    if no_llm:
        settings = Settings(**{**settings.model_dump(), "llm_enabled": False})

    effective_task = _task_from_str(task)

    # Determine ingestion source
    if log_file is not None:
        source = "file"          # batch: read once and stop
        source_path = str(log_file)
        if not log_file.exists():
            typer.echo(f"Error: file not found: {log_file}", err=True)
            raise typer.Exit(1)
    elif tail is not None:
        source = "file_tail"     # live: poll indefinitely
        source_path = str(tail)
        live = True
    elif live or not sys.stdin.isatty():
        source = "stdin"
        source_path = None
    else:
        typer.echo(
            "Provide a log file, --live, or pipe stdin.  Use --help for usage.", err=True
        )
        raise typer.Exit(1)

    run_id = _new_run_id()

    # Start server + pipeline
    asyncio.run(
        _run_batch_or_live(
            settings=settings,
            run_id=run_id,
            run_name=name,
            source=source,
            source_path=source_path,
            task=effective_task,
            port=port,
            headless=headless,
            export_format=export_format,
        )
    )


async def _run_batch_or_live(
    *,
    settings: Settings,
    run_id: str,
    run_name: str | None,
    source: str,
    source_path: str | None,
    task: TaskType | None,
    port: int,
    headless: bool,
    export_format: str | None,
) -> None:
    from model_story.ingester import make_ingester
    from model_story.pipeline import run_pipeline
    from model_story.server.app import create_app
    from model_story.server.hub import Hub
    from model_story.store.sqlite_store import RunStore

    store = RunStore(db_path=settings.db)
    hub = Hub()

    _app = create_app(settings=settings)
    # Override the app state with our pre-built store and hub
    _app.state.store = store
    _app.state.hub = hub
    _app.state.engine_map = {}

    ingester = make_ingester(
        source=source,
        run_id=run_id,
        path=source_path,
    )

    # Start the uvicorn server in a background task
    config = uvicorn.Config(
        _app,
        host=settings.host,
        port=port,
        log_level="warning",
        lifespan="off",  # we manage the lifespan manually
    )
    server = uvicorn.Server(config)

    async def _serve() -> None:
        await server.serve()

    server_task = asyncio.create_task(_serve())

    # Give the server a moment to start before opening the browser
    await asyncio.sleep(0.5)

    if not headless:
        _open_browser(port, run_id)
    else:
        typer.echo(f"  Run ID: {run_id}")

    try:
        finished_run = await run_pipeline(
            ingester=ingester,
            run_id=run_id,
            store=store,
            hub=hub,
            run_name=run_name,
            task=task,
        )
    finally:
        server.should_exit = True
        server.force_exit = True  # don't wait for in-flight connections
        try:
            await asyncio.wait_for(server_task, timeout=3.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            server_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await server_task

    # Print summary
    typer.echo("")
    typer.echo(f"  Run: {finished_run.name or finished_run.id}")
    grade = finished_run.final_grade
    typer.echo(f"  Grade: {grade.value if grade else 'N/A'}")
    typer.echo(f"  Task: {finished_run.task_type.value}")
    if finished_run.story_summary:
        typer.echo(f"\n  {finished_run.story_summary}\n")

    # Headless export
    if export_format and headless:
        _cli_export(run_id=run_id, fmt=export_format, store=store)


def _cli_export(run_id: str, fmt: str, store: RunStore, outfile: Path | None = None) -> None:
    outfile = outfile or Path(f"{run_id}.{fmt}")
    typer.echo(f"  Exporting {fmt.upper()} → {outfile}")

    if fmt == "json":
        import json

        run = store.get_run(run_id)
        frames = store.get_story_frames(run_id)
        events = store.get_metric_events(run_id)
        payload = {
            "run": run.model_dump(mode="json") if run else {},
            "frames": [f.model_dump(mode="json") for f in frames],
            "events": [e.model_dump(mode="json") for e in events],
        }
        outfile.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    elif fmt == "md":
        from model_story.exporters.markdown_export import build_markdown

        outfile.write_text(build_markdown(run_id=run_id, store=store), encoding="utf-8")
    elif fmt == "html":
        from model_story.exporters.html_export import build_html

        try:
            outfile.write_text(build_html(run_id=run_id, store=store), encoding="utf-8")
        except FileNotFoundError:
            typer.echo(
                "  HTML export needs the frontend bundle. Run `make build-frontend` first.",
                err=True,
            )
            raise typer.Exit(1) from None
    elif fmt == "pdf":
        from model_story.exporters.pdf_export import build_pdf

        try:
            outfile.write_bytes(build_pdf(run_id=run_id, store=store))
        except (NotImplementedError, ImportError):
            typer.echo(
                "  PDF export needs the 'pdf' extra: pip install 'model-story[pdf]'.",
                err=True,
            )
            raise typer.Exit(1) from None
    else:
        typer.echo(
            f"  Unknown export format: {fmt!r}. Use html, pdf, md, or json.", err=True
        )
        raise typer.Exit(1)


# ------------------------------------------------------------------
# Sub-commands
# ------------------------------------------------------------------


@app.command("serve")
def cmd_serve(
    port: int = typer.Option(7860, "--port", "-p", help="Port to listen on."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to."),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """Start the model-story server without processing a run."""
    _configure_logging(log_level)
    from model_story.server.app import create_app

    settings = get_settings()
    _app = create_app(settings=settings)

    # Loud warning when binding non-loopback with no auth token. The server
    # treats loopback clients as trusted for writes; binding publicly without
    # a token would otherwise let anyone reach the same machine create or
    # delete runs.
    if host not in {"127.0.0.1", "::1", "localhost"} and not settings.auth_token:
        typer.secho(
            f"⚠  Binding {host}:{port} without MODEL_STORY_AUTH_TOKEN — the "
            "server is exposed on the network with no authentication. "
            "Set MODEL_STORY_AUTH_TOKEN before publishing this endpoint.",
            fg=typer.colors.YELLOW, err=True,
        )

    typer.echo(f"Starting model-story server on http://{host}:{port}")
    uvicorn.run(_app, host=host, port=port, log_level=log_level.lower())


@app.command("list")
def cmd_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Max runs to show."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """List saved runs (newest first)."""
    _configure_logging(log_level)
    settings = get_settings()
    store = _open_store(settings)
    runs = store.list_runs(limit=limit)
    if not runs:
        typer.echo("No runs found.")
        return
    for run in runs:
        grade = run.final_grade.value if run.final_grade else "—"
        status = "✓" if run.finished_at else "⟳"
        typer.echo(
            f"  {status}  {run.id}  [{grade}]  {run.task_type.value}"
            f"  {run.started_at.strftime('%Y-%m-%d %H:%M')}"
            f"  {run.name or '(unnamed)'}"
        )


@app.command("open")
def cmd_open(
    run_id: str = typer.Argument(..., help="Run ID to open."),
    port: int = typer.Option(7860, "--port", "-p"),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Open a saved run in the browser."""
    _configure_logging(log_level)
    settings = get_settings()
    store = _open_store(settings)
    run = store.get_run(run_id)
    if run is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(1)
    from model_story.server.app import create_app

    _app = create_app(settings=settings)
    typer.echo(f"Opening run {run_id} …")
    webbrowser.open(f"http://127.0.0.1:{port}/v/{run_id}")
    uvicorn.run(_app, host="127.0.0.1", port=port, log_level="warning")


@app.command("export")
def cmd_export(
    run_id: str = typer.Argument(..., help="Run ID to export."),
    fmt: str = typer.Option("html", "--format", "-f", help="Format: html|pdf|md|json."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Export a run as HTML, PDF, Markdown, or JSON."""
    _configure_logging(log_level)
    settings = get_settings()
    store = _open_store(settings)
    if store.get_run(run_id) is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(1)
    _cli_export(run_id=run_id, fmt=fmt, store=store, outfile=output)


@app.command("prune")
def cmd_prune(
    older_than: str = typer.Option("30d", "--older-than", help="Delete runs older than N days."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List what would be deleted."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Delete runs older than a given age."""
    import re
    from datetime import datetime, timedelta, timezone

    _configure_logging(log_level)
    m = re.fullmatch(r"(\d+)d", older_than.strip())
    if not m:
        typer.echo("--older-than must be like '30d'", err=True)
        raise typer.Exit(1)
    days = int(m.group(1))
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    settings = get_settings()
    store = _open_store(settings)
    runs = store.list_runs(limit=10000)
    to_delete = [r for r in runs if r.started_at.replace(tzinfo=timezone.utc) < cutoff]

    if not to_delete:
        typer.echo("Nothing to prune.")
        return

    for run in to_delete:
        typer.echo(f"  {'[dry-run] ' if dry_run else ''}Deleting {run.id}  {run.started_at}")
        if not dry_run:
            store.delete_run(run.id)

    if not dry_run:
        typer.echo(f"  Pruned {len(to_delete)} run(s).")


@app.command("config")
def cmd_config(
    action: str = typer.Argument(..., help="show | set"),
    key: str | None = typer.Argument(None, help="Config key."),
    value: str | None = typer.Argument(None, help="Config value."),
) -> None:
    """Show or set configuration values.

    Config is read from environment variables (MODEL_STORY_*) or a .env file.
    Use ``set`` to write to .env in the current directory.
    """
    settings = get_settings()
    if action == "show":
        for field, val in settings.model_dump().items():
            typer.echo(f"  {field} = {val!r}")
    elif action == "set":
        if key is None or value is None:
            typer.echo("Usage: model-story config set <key> <value>", err=True)
            raise typer.Exit(1)
        env_key = f"MODEL_STORY_{key.upper()}"
        env_path = Path(".env")
        lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
        prefix = f"{env_key}="
        new_line = f"{env_key}={value}"
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                lines[i] = new_line
                updated = True
                break
        if not updated:
            lines.append(new_line)
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        typer.echo(f"  Set {env_key}={value}  (in {env_path})")
    else:
        typer.echo(f"Unknown action: {action!r}. Use 'show' or 'set'.", err=True)
        raise typer.Exit(1)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _open_store(settings: Settings) -> RunStore:
    from model_story.store.sqlite_store import RunStore

    return RunStore(db_path=settings.db)


# ------------------------------------------------------------------
# Console entry point
# ------------------------------------------------------------------

# Real subcommands. Anything else in first position is treated as a log file
# and routed to the implicit ``run`` command, so both of these work:
#   model-story train.log          (shorthand → `run train.log`)
#   model-story --live             (shorthand → `run --live`)
#   model-story serve --port 8000  (dispatches the serve subcommand)
_SUBCOMMANDS = frozenset({"run", "serve", "list", "open", "export", "prune", "config"})


def main_entry() -> None:
    """Console-script entry point (``model-story``).

    Typer cannot mix a positional argument on the group callback with
    subcommands without the subcommand name being swallowed as that argument.
    To keep the friendly ``model-story <log>`` shorthand *and* working
    subcommands, we route any invocation whose first positional token is not a
    known subcommand to the default ``run`` command.
    """
    argv = sys.argv[1:]

    # No args, or a top-level help flag → let Typer show the group help.
    if not argv or argv[0] in ("-h", "--help"):
        app()
        return

    first_positional = next((a for a in argv if not a.startswith("-")), None)
    if first_positional not in _SUBCOMMANDS:
        sys.argv = [sys.argv[0], "run", *argv]

    app()


if __name__ == "__main__":
    main_entry()
