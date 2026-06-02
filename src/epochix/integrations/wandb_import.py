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
            metrics: dict[str, float] = {}
            for col in history.columns:
                if col.startswith("_"):
                    continue  # skip W&B internal columns
                val = row[col]
                if val is None:
                    continue
                try:
                    metrics[str(col)] = float(val)
                except (TypeError, ValueError):
                    continue
            if metrics:
                reporter.log(**metrics)

    run_ms_id: str = reporter._run_id  # noqa: SLF001

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/v/{run_ms_id}")

    return run_ms_id
