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

import logging
import math
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
        import wandb  # type: ignore[import-not-found]
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

    # Fetch history as a pandas DataFrame
    history = wb_run.history(keys=keys, pandas=True)
    if history.empty:
        logger.warning("No history data found for run %s", run_id)
        return None

    from epochix.sdk.live_reporter import LiveReporter

    reporter = LiveReporter(name=name, port=port, open_browser=False)
    with reporter:
        for _, row in history.iterrows():
            metrics = _row_to_metrics(row, list(history.columns))
            if metrics:
                reporter.log(**metrics)

    run_ms_id: str = reporter._run_id  # noqa: SLF001

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/v/{run_ms_id}")

    return run_ms_id


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
