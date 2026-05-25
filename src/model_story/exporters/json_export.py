"""JSON export — Phase 11 placeholder."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model_story.store.sqlite_store import RunStore


def build_json(run_id: str, store: RunStore) -> str:  # pragma: no cover
    raise NotImplementedError("JSON exporter not yet implemented (Phase 11)")
