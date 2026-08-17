"""epochix CLI — one command to rule them all.

Entry point: ``epochix`` (configured in pyproject.toml).

Usage
-----
::

    epochix train.log                   # batch: parse file, open browser
    epochix --live                      # live: read stdin, open browser
    epochix --live --tail train.log     # live: tail file, open browser
    epochix --headless --export html    # CI: export HTML, no browser
    epochix serve --port 7860           # start server only
    epochix list                        # show saved runs
    epochix open <run_id>               # open a saved run in the browser
    epochix export <run_id> --format html|pdf|md|json
    epochix prune --older-than 30d      # delete old runs
    epochix config show
    epochix config set <key> <value>
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import uvicorn

from epochix.config import Settings, get_settings
from epochix.console import console_safe, console_symbols, harden_streams
from epochix.enums import TaskType

if TYPE_CHECKING:
    from epochix.store.sqlite_store import RunStore

app = typer.Typer(
    name="epochix",
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
            f"Unknown task type: {task_str!r}. Valid values: {[t.value for t in TaskType]}"
        ) from exc


# ------------------------------------------------------------------
# Main command: epochix [LOG_FILE]
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
    ssh: str | None = typer.Option(
        None,
        "--ssh",
        help="Tail a remote log over SSH: '[user@]host:/path/to/log'.",
        show_default=False,
    ),
    ssh_port: int | None = typer.Option(
        None,
        "--ssh-port",
        help="SSH port (default uses ~/.ssh/config).",
        show_default=False,
    ),
    ssh_identity: str | None = typer.Option(
        None,
        "--ssh-identity",
        help="Path to SSH private key.",
        show_default=False,
    ),
    ssh_opt: list[str] = typer.Option(
        [],
        "--ssh-opt",
        help="Extra ssh -o option(s); repeatable, e.g. --ssh-opt ProxyJump=bastion.",
        show_default=False,
    ),
    port: int = typer.Option(7860, "--port", "-p", help="Server port."),
    task: str | None = typer.Option(
        None, "--task", "-t", help="Force task type (e.g. biometric).", show_default=False
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM fallback parser."),
    headless: bool = typer.Option(False, "--headless", help="Do not open the browser."),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Print the run summary as JSON on stdout (implies --headless).",
    ),
    export_format: str | None = typer.Option(
        None,
        "--export",
        help="Export format (html|pdf|md|json|gif) in headless mode.",
        show_default=False,
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Where to write --export output (default: <run_id>.<format> here).",
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

    ssh_target_host: str | None = None
    ssh_remote_path: str | None = None
    if ssh is not None:
        from epochix.ingester.ssh import parse_ssh_target

        try:
            ssh_target_host, ssh_remote_path = parse_ssh_target(ssh)
        except ValueError as exc:
            typer.echo(f"Error: --ssh {exc}", err=True)
            raise typer.Exit(2) from exc

    # Determine ingestion source
    if ssh is not None:
        source = "ssh"
        source_path = ssh_remote_path
        live = True
    elif log_file is not None:
        source = "file"  # batch: read once and stop
        source_path = str(log_file)
        if not log_file.exists():
            typer.echo(f"Error: file not found: {log_file}", err=True)
            raise typer.Exit(1)
    elif tail is not None:
        source = "file_tail"  # live: poll indefinitely
        source_path = str(tail)
        live = True
    elif live or not sys.stdin.isatty():
        source = "stdin"
        source_path = None
    else:
        typer.echo(
            "Provide a log file, --live, --tail, --ssh, or pipe stdin. Use --help for usage.",
            err=True,
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
            # --json is for automation, which has no browser to open.
            headless=headless or json_out,
            json_out=json_out,
            export_format=export_format,
            export_output=output,
            ssh_target=ssh_target_host,
            ssh_port=ssh_port,
            ssh_identity=ssh_identity,
            ssh_opts=tuple(ssh_opt),
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
    json_out: bool,
    export_format: str | None,
    export_output: Path | None = None,
    ssh_target: str | None = None,
    ssh_port: int | None = None,
    ssh_identity: str | None = None,
    ssh_opts: tuple[str, ...] = (),
) -> None:
    from epochix.ingester import make_ingester
    from epochix.pipeline import run_pipeline
    from epochix.server.app import create_app
    from epochix.server.hub import Hub
    from epochix.store.sqlite_store import RunStore

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
        ssh_target=ssh_target,
        ssh_port=ssh_port,
        ssh_identity=ssh_identity,
        ssh_opts=ssh_opts,
    )

    # Start the uvicorn server in a background task
    _require_free_port(settings.host, port)
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
    elif not json_out:
        # --json owns stdout: anything else printed there would sit in front of
        # the document and break `json.load` for the caller.
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

    grade = finished_run.final_grade

    if json_out:
        # One JSON document on stdout and nothing else, so a caller can pipe
        # this straight into `json.load`. The GitHub Action does exactly that.
        typer.echo(
            json.dumps(
                {
                    "id": finished_run.id,
                    "name": finished_run.name,
                    "final_grade": grade.value if grade else None,
                    "task": finished_run.task_type.value,
                    "primary_metric": finished_run.primary_metric,
                    "story_summary": finished_run.story_summary,
                },
                # ASCII escapes, not raw characters. typer.echo hands the string
                # to stdout, which encodes with the process locale — cp1252 on
                # Windows, where the em dash the narratives are full of becomes
                # the single byte 0x97. JSON is defined as UTF-8, so piping this
                # into json.load died with "invalid start byte". It was
                # intermittent, because the template is chosen from a hash of
                # the run id: the same log emitted valid output one run and
                # undecodable output the next. \\uXXXX is valid under every
                # encoding and json.load restores the character.
                ensure_ascii=True,
            )
        )
    else:
        # Print summary
        typer.echo("")
        typer.echo(f"  Run: {finished_run.name or finished_run.id}")
        typer.echo(f"  Grade: {grade.value if grade else 'N/A'}")
        typer.echo(f"  Task: {finished_run.task_type.value}")
        if finished_run.story_summary:
            typer.echo(f"\n  {finished_run.story_summary}\n")

    # Headless export
    if export_format and headless:
        _cli_export(
            run_id=run_id,
            fmt=export_format,
            store=store,
            outfile=export_output,
            quiet=json_out,
        )


def _require_free_port(host: str, port: int) -> None:
    """Fail with a usable message instead of a raw OSError traceback.

    The server is started as a background asyncio task, so a bind failure
    surfaced as an unhandled OSError stack trace with no hint about what to do.
    """
    import socket

    # No SO_REUSEADDR: we want the bind to fail exactly when something else is
    # already listening, on Windows as well as POSIX.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            typer.secho(
                f"Port {port} on {host} is already in use.",
                fg=typer.colors.RED,
                err=True,
            )
            typer.echo(
                f"  Another epochix server may already be running. "
                f"Try a different port:  --port {port + 1}",
                err=True,
            )
            raise typer.Exit(1) from None


def _cli_export(
    run_id: str,
    fmt: str,
    store: RunStore,
    outfile: Path | None = None,
    metric: str | None = None,
    chart: str = "curve",
    # `--json` owns stdout: one document and nothing else, or the caller's
    # json.load fails on "Extra data". The guard added in 0.5.80 covered the
    # line printed BEFORE the document and missed the export confirmation
    # printed after it, so `run --json --export md` emitted invalid JSON.
    quiet: bool = False,
) -> None:
    outfile = outfile or Path(f"{run_id}.{fmt}")

    def say(message: str) -> None:
        """Progress chatter — to stderr when stdout is carrying JSON.

        Errors already go to stderr unconditionally; only the informational
        lines need redirecting, and they must still be SEEN, so stderr rather
        than silence.
        """
        typer.echo(message, err=quiet)

    # Absolute: the default lands in the current directory, and "Exporting HTML
    # -> 01K….html" left people hunting for a file they could not place.
    say(f"  Exporting {fmt.upper()} {console_symbols()[0]} {outfile.resolve()}")

    # `--output reports/run.md` should work without a prior mkdir.
    try:
        if outfile.parent != Path():
            outfile.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        typer.echo(f"  Cannot create {outfile.parent}: {exc.strerror}", err=True)
        raise typer.Exit(1) from None

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
        from epochix.exporters.markdown_export import build_markdown

        outfile.write_text(build_markdown(run_id=run_id, store=store), encoding="utf-8")
    elif fmt == "html":
        from epochix.exporters.html_export import build_html

        try:
            outfile.write_text(build_html(run_id=run_id, store=store), encoding="utf-8")
        except FileNotFoundError:
            typer.echo(
                "  HTML export needs the frontend bundle. Run `make build-frontend` first.",
                err=True,
            )
            raise typer.Exit(1) from None
    elif fmt == "gif":
        from epochix.exporters.gif_export import build_gif, build_overlay_gif

        try:
            if chart == "overlay":
                outfile.write_bytes(build_overlay_gif(run_id=run_id, store=store))
            else:
                outfile.write_bytes(build_gif(run_id=run_id, store=store, metric=metric))
        except NotImplementedError as exc:
            typer.echo(f"  {exc}", err=True)
            raise typer.Exit(1) from None
        except ValueError as exc:
            typer.echo(f"  Cannot animate this run: {exc}", err=True)
            raise typer.Exit(1) from None
    elif fmt == "pdf":
        from epochix.exporters.pdf_export import build_pdf

        try:
            outfile.write_bytes(build_pdf(run_id=run_id, store=store))
        except (NotImplementedError, ImportError, OSError) as exc:
            # OSError included: `pip install weasyprint` succeeds on Windows and
            # then the import dies loading GTK. Telling that user to install the
            # extra they just installed is worse than useless, so print the
            # exporter's own message — it names both causes and offers the
            # no-install route (export HTML, print to PDF from the browser).
            typer.echo(f"  {exc}", err=True)
            raise typer.Exit(1) from None
    else:
        typer.echo(f"  Unknown export format: {fmt!r}. Use html, pdf, md, or json.", err=True)
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
    """Start the epochix server without processing a run."""
    _configure_logging(log_level)
    from epochix.server.app import create_app

    settings = get_settings()
    _app = create_app(settings=settings)

    # Loud warning when binding non-loopback with no auth token. The server
    # treats loopback clients as trusted for writes; binding publicly without
    # a token would otherwise let anyone reach the same machine create or
    # delete runs.
    if host not in {"127.0.0.1", "::1", "localhost"} and not settings.auth_token:
        typer.secho(
            f"⚠  Binding {host}:{port} without EPOCHIX_AUTH_TOKEN — the "
            "server is exposed on the network with no authentication. "
            "Set EPOCHIX_AUTH_TOKEN before publishing this endpoint.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    _require_free_port(host, port)
    typer.echo(f"Starting epochix server on http://{host}:{port}")
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
    _, tick, _, spin = console_symbols()
    for run in runs:
        grade = run.final_grade.value if run.final_grade else "-"
        status = tick if run.finished_at else spin
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
    from epochix.server.app import create_app

    _app = create_app(settings=settings)
    typer.echo(console_safe(f"Opening run {run_id} …"))
    webbrowser.open(f"http://127.0.0.1:{port}/v/{run_id}")
    uvicorn.run(_app, host="127.0.0.1", port=port, log_level="warning")


@app.command("export")
def cmd_export(
    run_id: str = typer.Argument(..., help="Run ID to export."),
    fmt: str = typer.Option("html", "--format", "-f", help="Format: html|pdf|md|json|gif."),
    metric: str | None = typer.Option(
        None,
        "--metric",
        "-m",
        help="GIF only: which metric to animate (default: the run's primary metric).",
    ),
    chart: str = typer.Option(
        "curve",
        "--chart",
        help="GIF only: curve|overlay. 'overlay' draws train vs val, marking the best epoch.",
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output path."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Export a run as HTML, PDF, Markdown, JSON, or an animated GIF."""
    _configure_logging(log_level)
    settings = get_settings()
    store = _open_store(settings)
    if store.get_run(run_id) is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(1)
    _cli_export(run_id=run_id, fmt=fmt, store=store, outfile=output, metric=metric, chart=chart)


@app.command("race")
def cmd_race(
    run_ids: list[str] = typer.Argument(..., help="Two or more run IDs to race."),
    metric: str | None = typer.Option(
        None, "--metric", "-m", help="Metric to race on (default: one they share)."
    ),
    output: Path = typer.Option(Path("race.gif"), "--output", "-o", help="Output path."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Animate several runs racing on one metric — the version for a slide.

    Curves align by epoch, so runs of different lengths finish at different
    moments. That is the honest picture: reaching 0.95 in 8 epochs is not the
    same result as reaching it in 40.
    """
    _configure_logging(log_level)
    settings = get_settings()
    store = _open_store(settings)

    for rid in run_ids:
        if store.get_run(rid) is None:
            typer.echo(f"Run not found: {rid}", err=True)
            raise typer.Exit(1)

    from epochix.exporters.gif_export import build_comparison_gif

    try:
        data = build_comparison_gif(list(run_ids), store, metric=metric)
    except NotImplementedError as exc:
        typer.echo(f"  {exc}", err=True)
        raise typer.Exit(1) from None
    except ValueError as exc:
        typer.echo(f"  Cannot race these runs: {exc}", err=True)
        raise typer.Exit(1) from None

    output.write_bytes(data)
    typer.echo(f"  Race GIF -> {output}")


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


@app.command("demo")
def cmd_demo(
    name: str = typer.Argument(
        "seq2seq",
        help="Which bundled demo to load: seq2seq · yolov8 · keras.",
    ),
    port: int = typer.Option(7860, "--port", "-p", help="Server port."),
    headless: bool = typer.Option(False, "--headless", help="Do not open the browser."),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    """Visualise a bundled demo log — no training of your own needed.

    Newcomers can see the dashboard in one command::

        epochix demo            # seq2seq + attention (NLP)
        epochix demo yolov8     # YOLO object detection
        epochix demo keras      # Keras image classifier
    """
    from importlib.resources import files

    _configure_logging(log_level)

    aliases = {
        "seq2seq": "seq2seq_attention.log",
        "yolov8": "yolov8_detection.log",
        "yolo": "yolov8_detection.log",
        "keras": "keras_image_classifier.log",
    }
    fname = aliases.get(name.lower(), name)
    demo_root = files("epochix").joinpath("_demos")
    demo_path = demo_root.joinpath(fname)
    if not demo_path.is_file():
        available = ", ".join(sorted(aliases))
        typer.secho(
            f"Demo {name!r} not found. Available: {available}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    typer.secho(
        console_safe(f"▶ Running bundled demo: {fname}"),
        fg=typer.colors.CYAN,
    )
    # Reuse the regular `run` path so behaviour matches what users see with
    # their own logs (parsing, story engine, browser open).
    cmd_run(
        log_file=Path(str(demo_path)),
        live=False,
        tail=None,
        ssh=None,
        ssh_port=None,
        ssh_identity=None,
        ssh_opt=[],
        port=port,
        task=None,
        no_llm=True,
        headless=headless,
        json_out=False,
        export_format=None,
        name=f"Demo · {fname}",
        log_level=log_level,
    )


@app.command("check")
def cmd_check(
    log_file: Path = typer.Argument(..., help="Training log to inspect."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Explain what epochix can and cannot read from a log - and what to add.

    Nothing is stored or served; this only reports. Use it when the dashboard
    looks empty or the grade seems wrong, to see exactly which parser matched,
    which metrics were found, and what is missing.
    """
    _configure_logging(log_level)

    if not log_file.is_file():
        typer.echo(f"No such file: {log_file}", err=True)
        raise typer.Exit(1)

    from epochix.normalizer import normalize
    from epochix.parsers.architecture_parser import parse_architecture
    from epochix.parsers.base import ParserContext
    from epochix.parsers.registry import SNIFF_SAMPLE_LINES, detect_parser
    from epochix.pipeline import _clean_line
    from epochix.story_engine.task_classifier import classify_task

    raw_lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = [_clean_line(ln) for ln in raw_lines]
    if not lines:
        typer.echo("The file is empty - nothing to parse.")
        raise typer.Exit(1)

    parser = detect_parser(lines[:SNIFF_SAMPLE_LINES])
    ctx = ParserContext(run_id="check")
    # name -> [count, first, last, any_epoch]
    found: dict[str, list[float]] = {}
    seen_keys: set[str] = set()
    epochs: set[float] = set()

    for i, line in enumerate(lines):
        ctx.seq = i
        for raw in parser.parse_line(line, ctx):
            try:
                event = normalize(raw, run_id="check")
            except ValueError:
                continue
            seen_keys.add(event.canonical_key)
            if event.epoch is not None:
                epochs.add(event.epoch)
            entry = found.get(event.canonical_key)
            if entry is None:
                found[event.canonical_key] = [1, event.value, event.value]
            else:
                entry[0] += 1
                entry[2] = event.value

    task = classify_task(seen_keys)
    arch = parse_architecture(lines)
    arrow, tick, cross, _ = console_symbols()

    typer.echo("")
    typer.echo(f"  file          {log_file}")
    typer.echo(f"  lines         {len(lines)}")
    typer.echo(f"  parser        {parser.name}")
    typer.echo(f"  task          {task.value}")
    typer.echo(f"  epochs seen   {len(epochs) or '-'}")
    typer.echo("")

    if found:
        typer.echo("  metrics found")
        for key in sorted(found):
            count, first, last = found[key]
            typer.echo(f"    {key:<16} {int(count):>4} values   {first:.4g} {arrow} {last:.4g}")
    else:
        typer.echo("  metrics found   (none)")
    typer.echo("")

    # ── actionable gaps ──────────────────────────────────────────────────────
    problems: list[str] = []

    if not found:
        problems.append(
            "No metrics were recognised at all.\n"
            "      Print one line per epoch containing key=value pairs, e.g.\n"
            '        print(f"Epoch {epoch}/{total} train_loss={loss:.4f} '
            'val_accuracy={acc:.4f}")'
        )
    elif task is TaskType.CUSTOM:
        problems.append(
            "No task-defining metric (accuracy / mAP / F1 / MAE / perplexity ...),\n"
            "      so the run is graded on how much its loss improved rather than on\n"
            "      task quality. Log one to get a real grade, e.g.\n"
            '        print(f"Epoch {epoch}/{total} train_loss={loss:.4f} '
            'val_accuracy={acc:.4f}")'
        )
    elif task is TaskType.REGRESSION and not (seen_keys & {"R2", "val_R2"}):
        problems.append(
            "No R2, so the grade reflects how much the error IMPROVED, not how\n"
            "      good the model is. MAE and RMSE are in your target's units - an\n"
            "      MAE of 9.8 is excellent for house prices and terrible for a\n"
            "      probability - so they cannot be scored on an absolute scale.\n"
            "      R2 can: log it for a grade that means something.\n"
            '        print(f"R2: {r2_score(y_true, y_pred):.4f}")'
        )

    if not epochs:
        problems.append(
            "No epoch numbers were found, so the progress bar cannot advance.\n"
            '      Include the epoch on the metric line: "Epoch 3/20 ..." or "epoch=3".'
        )

    if not arch:
        problems.append(
            "No model architecture - the Network panel will stay empty.\n"
            "      Either print the model summary once at the start (Keras\n"
            "      model.summary(), torchinfo, or plain print(model)), or use the SDK:\n"
            "        from epochix.sdk import LiveReporter\n"
            "        with LiveReporter(model=model) as r: r.log(...)"
        )

    if problems:
        typer.echo("  to improve this run")
        for p in problems:
            typer.echo(f"    {cross} {p}")
    else:
        typer.echo(f"  {tick} everything epochix needs is present ({len(arch)} layers detected)")
    typer.echo("")


@app.command("doctor")
def cmd_doctor() -> None:
    """Print diagnostics to paste into a bug report.

    Deliberately reports only what is needed to reproduce a problem: versions,
    which optional extras resolve, whether the dashboard bundle shipped, and
    how many runs the database holds. No run names, no file paths, no log
    contents — a run name comes from a log file and is not ours to publish.
    """
    import platform
    import sys
    from importlib.metadata import version as _pkg_version

    lines: list[str] = ["<!-- epochix doctor -->", "```"]

    try:
        ver = _pkg_version("epochix")
    except Exception:  # pragma: no cover - source checkout without metadata
        ver = "unknown (source checkout)"
    lines.append(f"epochix        {ver}")
    lines.append(f"python         {sys.version.split()[0]} ({platform.python_implementation()})")
    lines.append(f"platform       {platform.system()} {platform.release()} {platform.machine()}")

    # Capabilities, not extras. GIF and PDF ship in the base install now, so
    # their libraries are listed to prove they are THERE — doctor kept probing
    # weasyprint after PDF moved to fpdf2 and reported "PDF export unavailable"
    # while PDF worked, which is the exact false statement this tool exists to
    # avoid. Only `llm` is genuinely optional.
    for extra, module, what in (
        ("gif", "PIL", "animated GIF export"),
        ("pdf", "fpdf", "PDF export"),
        ("llm", "httpx", "LLM fallback parser"),
    ):
        try:
            __import__(module)
            state = "installed"
        except ImportError:
            state = f"MISSING - {what} unavailable (pip install 'epochix[{extra}]')"
        except Exception as exc:  # noqa: BLE001
            # `doctor` is what you run WHEN SOMETHING IS WRONG, so it must not
            # be the thing that breaks. weasyprint imports cleanly from pip and
            # then raises OSError loading GTK — that took the whole command down
            # with a traceback on exactly the machine someone would run it on.
            # Report the broken import as a finding; that IS the diagnosis.
            state = f"BROKEN - installed but fails to import: {type(exc).__name__}: {exc}"
            state = console_safe(state.replace("\n", " "))[:160]
        lines.append(f"extra {extra:<10} {state}")

    # The dashboard is vendored into the wheel at release time. When it is
    # absent every HTML export and the whole web UI 501s, which reads like a
    # server fault and is not one.
    dist = Path(__file__).resolve().parent / "_frontend" / "dist" / "index.html"
    bundled = "bundled" if dist.is_file() else "MISSING (index.html not vendored)"
    lines.append(f"dashboard      {bundled}")

    settings = get_settings()
    try:
        store = _open_store(settings)
        runs = store.list_runs(limit=1000)
        total = len(runs) if isinstance(runs, list) else 0
        lines.append(f"database       ok, {total} run(s)")
    except Exception as exc:
        lines.append(f"database       ERROR {type(exc).__name__}: {exc}")

    lines.append("```")
    lines.append("")
    lines.append("Report a problem: https://github.com/Epochix-dev/epochix/issues/new")
    lines.append("If a number or a sentence looks WRONG rather than broken, say so -")
    lines.append("that is the kind of bug this project most wants to hear about.")
    typer.echo("\n".join(lines))


@app.command("config")
def cmd_config(
    action: str = typer.Argument(..., help="show | set"),
    key: str | None = typer.Argument(None, help="Config key."),
    value: str | None = typer.Argument(None, help="Config value."),
) -> None:
    """Show or set configuration values.

    Config is read from environment variables (EPOCHIX_*) or a .env file.
    Use ``set`` to write to .env in the current directory.
    """
    settings = get_settings()
    if action == "show":
        for field, val in settings.model_dump().items():
            typer.echo(f"  {field} = {val!r}")
    elif action == "set":
        if key is None or value is None:
            typer.echo("Usage: epochix config set <key> <value>", err=True)
            raise typer.Exit(1)
        # Accept both "port" and "EPOCHIX_PORT" — blindly prefixing turned the
        # latter into EPOCHIX_EPOCHIX_PORT, a key nothing ever reads.
        bare = key.upper().removeprefix("EPOCHIX_")
        env_key = f"EPOCHIX_{bare}"
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
    from epochix.store.sqlite_store import RunStore

    return RunStore(db_path=settings.db)


# ------------------------------------------------------------------
# Console entry point
# ------------------------------------------------------------------


@app.command("import-tensorboard")
def cmd_import_tensorboard(
    logdir: Path = typer.Argument(..., help="TensorBoard log directory (events.out.tfevents.*)."),
    port: int = typer.Option(7860, "--port", "-p", help="Server port."),
    name: str | None = typer.Option(None, "--name", "-n", help="Run name.", show_default=False),
    headless: bool = typer.Option(False, "--headless", help="Do not open the browser."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Turn an existing TensorBoard logdir into an epochix story.

    Needs no account and no network: the scalars are read straight off disk.
    """
    _configure_logging(log_level)
    if not logdir.exists():
        typer.echo(f"Error: logdir not found: {logdir}", err=True)
        raise typer.Exit(1)

    # The importer starts its own server through LiveReporter, so a busy port
    # is a bind failure inside a background asyncio task — surfacing as a raw
    # uvicorn traceback and SystemExit(3). `run` has guarded this since 0.5.32;
    # these commands were added without it, and the likeliest reason 7860 is
    # taken is that the user already has an epochix dashboard open.
    _require_free_port(get_settings().host, port)

    from epochix.integrations.tensorboard_import import import_tensorboard

    try:
        runs = import_tensorboard(logdir, port=port, open_browser=not headless, run_name=name)
    except ImportError as exc:
        typer.echo(f"  {exc}", err=True)
        raise typer.Exit(1) from None
    if not runs:
        typer.echo(
            "  No scalar events found. Point this at the directory holding "
            "events.out.tfevents.* files.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"  Imported {len(runs)} run(s) from {logdir}")


@app.command("import-wandb")
def cmd_import_wandb(
    run_ref: str = typer.Argument(
        ...,
        help="A local wandb/ path (no account needed), or 'entity/project/run_id'.",
    ),
    port: int = typer.Option(7860, "--port", "-p", help="Server port."),
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        help="W&B API key. Falls back to the WANDB_API_KEY environment variable.",
        show_default=False,
    ),
    headless: bool = typer.Option(False, "--headless", help="Do not open the browser."),
    log_level: str = typer.Option("WARNING", "--log-level"),
) -> None:
    """Turn an existing Weights & Biases run into an epochix story.

    Give it a PATH — your wandb/ directory, one run directory inside it, or a
    .wandb file — and everything is read off local disk: no account, no key,
    no network. Give it 'entity/project/run_id' instead and it fetches from
    the W&B API, which does need credentials.
    """
    _configure_logging(log_level)

    # A path that exists is a local run: read it off disk, no credentials.
    # This is the common case for anyone who already has a wandb/ directory,
    # and it is checked first so the account-only path is the fallback rather
    # than the entry price.
    _require_free_port(get_settings().host, port)

    local = Path(run_ref)
    if local.exists():
        from epochix.integrations.wandb_import import import_wandb_dir

        try:
            ids = import_wandb_dir(local, port=port, open_browser=not headless)
        except (FileNotFoundError, ImportError) as exc:
            typer.echo(f"  {exc}", err=True)
            raise typer.Exit(1) from None
        if not ids:
            typer.echo(f"  No run history found under {local}.", err=True)
            raise typer.Exit(1)
        typer.echo(f"  Imported {len(ids)} run(s) from {local}")
        return

    parts = run_ref.split("/")
    if len(parts) != 3 or not all(parts):
        typer.echo(
            f"Error: expected 'entity/project/run_id', got {run_ref!r}.",
            err=True,
        )
        raise typer.Exit(2)
    entity, project, run_id = parts

    from epochix.integrations.wandb_import import import_wandb

    try:
        imported = import_wandb(
            entity=entity,
            project=project,
            run_id=run_id,
            port=port,
            open_browser=not headless,
            api_key=api_key,
        )
    except ImportError as exc:
        typer.echo(f"  {exc}", err=True)
        raise typer.Exit(1) from None
    if imported is None:
        typer.echo(f"  No history found for {run_ref}.", err=True)
        raise typer.Exit(1)
    typer.echo(f"  Imported {run_ref} as {imported}")


# Real subcommands. Anything else in first position is treated as a log file
# and routed to the implicit ``run`` command, so both of these work:
#   epochix train.log          (shorthand → `run train.log`)
#   epochix --live             (shorthand → `run --live`)
#   epochix serve --port 8000  (dispatches the serve subcommand)
def _subcommand_names() -> frozenset[str]:
    """Names of every registered subcommand, read from the Typer app itself.

    This used to be a hardcoded set, so a newly added command was silently
    unreachable — the router treated its name as a log-file path and handed it
    to ``run`` ("Got unexpected extra argument"). Deriving it means adding a
    command is enough.
    """
    names: set[str] = set()
    for cmd in app.registered_commands:
        if cmd.name:
            names.add(cmd.name)
        elif cmd.callback is not None:
            names.add(cmd.callback.__name__.removeprefix("cmd_").replace("_", "-"))
    return frozenset(names)


# Derived once at import — after every @app.command above has registered.
_SUBCOMMANDS = _subcommand_names()


def main_entry() -> None:
    """Console-script entry point (``epochix``).

    Typer cannot mix a positional argument on the group callback with
    subcommands without the subcommand name being swallowed as that argument.
    To keep the friendly ``epochix <log>`` shorthand *and* working
    subcommands, we route any invocation whose first positional token is not a
    known subcommand to the default ``run`` command.
    """
    harden_streams()
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
