"""Weights & Biases run importer.

Fetches scalar history from a W&B run via the W&B public API and
converts it into epochix events fed through the standard pipeline.

Usage::

    # CLI
    epochix import-wandb --entity myorg --project bert-finetune --run-id abc123

    # Python
    from epochix.integrations.wandb_import import import_wandb
    run = import_wandb(entity="myorg", project="bert-finetune", run_id="abc123")

``wandb`` is an optional dependency — imported lazily.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def import_wandb(
    *,
    entity: str,
    project: str,
    run_id: str,
    port: int = 7860,
    open_browser: bool = True,
    api_key: str | None = None,
    keys: list[str] | None = None,
) -> Any:  # noqa: ANN401
    """Import scalar history from a Weights & Biases run.

    Parameters
    ----------
    entity:
        W&B entity (username or team name).
    project:
        W&B project name.
    run_id:
        W&B run ID (8-character alphanumeric string).
    port:
        Port of the epochix server.
    open_browser:
        Open the dashboard after importing.
    api_key:
        W&B API key.  Falls back to ``WANDB_API_KEY`` env var if not set.
    keys:
        Metric keys to import (default: all scalars).

    Returns
    -------
    str
        The epochix run ID.
    """
    try:
        import wandb
    except ImportError as exc:
        raise ImportError(
            "wandb is required for W&B import. Install with: pip install wandb"
        ) from exc

    if api_key:
        wandb.login(key=api_key, relogin=True)

    api = wandb.Api()
    wb_run = api.run(f"{entity}/{project}/{run_id}")

    name = wb_run.name or run_id
    logger.info("Importing W&B run '%s' (%s/%s/%s)", name, entity, project, run_id)

    # scan_history, NOT history: `history()` takes `samples=500` and returns a
    # DOWNSAMPLE — its own docstring says "if you are ok with the history
    # records being sampled". Importing a 2000-epoch run through it produced
    # 500 interpolated-looking points presented as the run, which moves the
    # final value, the peak, and the best-epoch call. Reporting the wrong best
    # epoch is precisely the kind of false statement this project refuses to
    # make. scan_history pages through every record.
    #
    # It also yields plain dicts, so pandas is no longer implicitly required.
    from epochix.sdk.live_reporter import LiveReporter

    reporter = LiveReporter(name=name, port=port, open_browser=False)
    logged = 0
    with reporter:
        for row in wb_run.scan_history(keys=keys):
            metrics = _row_to_metrics(row, list(row))
            if metrics:
                reporter.log(**metrics)
                logged += 1

    if logged == 0:
        logger.warning("No history data found for run %s", run_id)
        return None

    run_ms_id: str = reporter._run_id  # noqa: SLF001

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/v/{run_ms_id}")

    return run_ms_id


def _scan_wandb_file(path: Path) -> tuple[str | None, list[dict[str, float]]]:
    """(run name, history rows) from a local ``run-*.wandb`` file.

    W&B stores a run's history ONLY in this binary file — there is no
    ``wandb-summary.json`` or ``output.log`` to fall back on, which is easy to
    assume and wrong. It is a length-prefixed record log of protobuf
    ``Record`` messages, read here with wandb's own ``DataStore`` and protobuf
    definitions, so no account, key or network is involved.

    History items carry the metric name in ``nested_key`` (not ``key``) and the
    value as a JSON string. ``_step``/``_timestamp``/``_runtime`` are
    bookkeeping.
    """
    from wandb.proto import wandb_internal_pb2 as pb
    from wandb.sdk.internal.datastore import DataStore

    store = DataStore()
    store.open_for_scan(str(path))

    name: str | None = None
    rows: list[dict[str, float]] = []
    while True:
        data = store.scan_data()
        if data is None:
            break
        record = pb.Record()
        record.ParseFromString(bytes(data))
        kind = record.WhichOneof("record_type")
        if kind == "run" and name is None:
            name = record.run.display_name or record.run.run_id or None
        elif kind == "history":
            raw: dict[str, Any] = {}
            for item in record.history.item:
                key = item.nested_key[0] if item.nested_key else item.key
                if not key:
                    continue
                try:
                    raw[key] = json.loads(item.value_json)
                except (ValueError, TypeError):
                    continue
            metrics = _row_to_metrics(raw, list(raw))
            if metrics:
                rows.append(metrics)
    return name, rows


def import_wandb_dir(
    path: str | Path,
    *,
    port: int = 7860,
    open_browser: bool = True,
    run_name: str | None = None,
) -> list[str]:
    """Import W&B runs already on disk — no account, no key, no network.

    *path* may be the ``wandb/`` directory a training script created, a single
    ``run-*``/``offline-run-*`` directory inside it, or a ``.wandb`` file.

    This is the counterpart to :func:`import_wandb`, which reaches the W&B API
    and therefore needs credentials. Everything here comes off the local disk,
    so a run logged with ``WANDB_MODE=offline`` — or any run whose directory
    still exists — can be read with nothing but ``wandb`` installed.

    Returns the epochix run ids created, one per W&B run found.
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"No such path: {root}")

    if root.is_file():
        files = [root]
    else:
        # A run directory holds the file directly; a wandb/ directory holds
        # one level of run directories.
        files = sorted(root.glob("run-*.wandb")) or sorted(root.glob("*/run-*.wandb"))
    if not files:
        raise FileNotFoundError(
            f"No run-*.wandb file under {root}. Point this at your wandb/ "
            f"directory, a run directory inside it, or the .wandb file itself."
        )

    from epochix.sdk.live_reporter import LiveReporter

    created: list[str] = []
    for wandb_file in files:
        name, rows = _scan_wandb_file(wandb_file)
        if not rows:
            logger.warning("No history in %s — skipping", wandb_file.name)
            continue

        reporter = LiveReporter(
            name=run_name or name or wandb_file.stem,
            port=port,
            open_browser=False,
        )
        with reporter:
            for row in rows:
                reporter.log(**row)
        created.append(reporter._run_id)  # noqa: SLF001

    if created and open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/v/{created[0]}")
    return created


def _row_to_metrics(row: Any, columns: list[str]) -> dict[str, float]:  # noqa: ANN401
    """One row of a W&B history frame → the metrics for one epoch.

    W&B keeps the step in the internal ``_step`` column, and every ``_``-prefixed
    column is bookkeeping (``_runtime``, ``_timestamp``). Skipping all of them
    dropped the step too, so imported runs had no epoch at all — the dashboard
    showed "Epoch —" and a dead progress bar. Fall back to ``_step`` when the
    user didn't log an explicit ``epoch``.

    Sparse histories (a metric logged every N steps) leave NaN holes; those are
    dropped here rather than shipped as fake zeroes.
    """
    metrics: dict[str, float] = {}

    for col in columns:
        if col.startswith("_"):
            continue
        value = _as_finite_float(row[col])
        if value is not None:
            metrics[str(col)] = value

    if not metrics:
        return {}

    if "epoch" not in metrics and "_step" in columns:
        step = _as_finite_float(row["_step"])
        if step is not None:
            metrics["epoch"] = step

    return metrics


def _as_finite_float(value: object) -> float | None:
    """float(value) or None — NaN/±Inf and non-numerics included."""
    if value is None:
        return None
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None
