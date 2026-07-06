"""JSON export — canonical, re-importable run payload.

Single source of truth for the run-JSON shape used by the HTTP export route,
the SDK ``export(fmt="json")`` path, and the HTML export's embedded data.
Round-trips via ``Run.model_validate`` / ``MetricEvent.model_validate``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from epochix.store.sqlite_store import RunStore


def build_json_payload(run_id: str, store: RunStore) -> dict[str, Any]:
    """Return the canonical run payload as a plain dict.

    Raises
    ------
    ValueError
        If the run is not found in the store.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")
    return {
        "run": run.model_dump(mode="json"),
        "frames": [f.model_dump(mode="json") for f in store.get_story_frames(run_id)],
        "events": [e.model_dump(mode="json") for e in store.get_metric_events(run_id)],
    }


def build_json(run_id: str, store: RunStore) -> str:
    """Serialise the canonical run payload to an indented JSON string."""
    return json.dumps(build_json_payload(run_id, store), indent=2)
