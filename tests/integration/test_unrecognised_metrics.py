"""Metrics we do not know by name keep their own names — and their own series.

Every unrecognised key used to be filed under one canonical name, "custom", so
two unrelated measurements became one curve. A reinforcement-learning log
printing `reward` and `entropy` was narrated as a single series alternating
between them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from epochix.exporters._pdf_render import _unrecognised_keys
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

REWARD = [1.0, 2.5, 4.0, 6.0, 7.5, 9.0]
ENTROPY = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]


def _run(tmp_path: Path, lines: list[str]) -> RunStore:
    log = tmp_path / "rl.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("u", str(log)), run_id="u", store=store, hub=Hub())
    )
    return store


def test_two_unrecognised_metrics_stay_two_series(tmp_path: Path) -> None:
    lines = [
        f"iter {i} reward={r} entropy={e}"
        for i, (r, e) in enumerate(zip(REWARD, ENTROPY, strict=True), start=1)
    ]
    store = _run(tmp_path, lines)

    events = store.get_metric_events("u")
    by_key: dict[str, list[float]] = {}
    for event in events:
        by_key.setdefault(event.canonical_key, []).append(event.value)
    assert by_key == {"reward": REWARD, "entropy": ENTROPY}

    frames = store.get_story_frames("u")
    assert {f.primary_metric for f in frames} == {"reward"}
    assert [f.primary_metric_value for f in frames] == REWARD

    # And the PDF charts each as its own series.
    assert sorted(_unrecognised_keys(events)) == ["entropy", "reward"]


def test_a_number_in_prose_is_not_a_metric(tmp_path: Path) -> None:
    """Printed once, an unknown name is indistinguishable from prose."""
    store = _run(
        tmp_path,
        ["Server listening on port 8080", "Response sent: 200 OK", "Numbers but no keys: 0.234"],
    )
    assert store.get_metric_events("u") == []
    assert store.get_story_frames("u") == []
