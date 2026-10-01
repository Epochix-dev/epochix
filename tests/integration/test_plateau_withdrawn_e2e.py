"""A real Keras run, through the whole pipeline: its mid-run plateau is withdrawn.

The recorded Keras demo moved less than 1% over epochs 10-14, climbed again,
and flattened over its last five epochs. The plateau warning fired once at
epoch 14 and stood — in words that said the model "has stopped finding new
patterns" — beside a grade card reading "still improving at the last reading".

Unit tests replay numbers; this drives the logs the way `epochix run` does and
checks what the frames carry to the dashboard and what the report prints.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from epochix.exporters.markdown_export import build_markdown
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.messages import message
from epochix.story_engine.warnings import standing_warnings

REPO = Path(__file__).resolve().parents[2]
KERAS = REPO / "demo" / "keras_image_classifier.log"
RESNET = REPO / "tests" / "fixtures" / "logs" / "resnet18_cifar10.log"


def _told(log: Path) -> tuple[RunStore, list[StoryFrame]]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("r", str(log)), run_id="r", store=store, hub=Hub())
    )
    return store, store.get_story_frames("r")


def _standing_at(frames: list[StoryFrame], epoch: float) -> list[str]:
    seen = (w for f in frames if f.epoch is not None and f.epoch <= epoch for w in f.warnings)
    return [w.kind for w in standing_warnings(seen)]


def test_the_plateau_warning_is_withdrawn_when_the_metric_moves_again() -> None:
    _, frames = _told(KERAS)
    plateau = [
        (f.epoch, w.kind) for f in frames for w in f.warnings if w.kind.startswith("plateau")
    ]
    assert plateau == [(14.0, "plateau"), (15.0, "plateau_cleared"), (19.0, "plateau")]
    assert _standing_at(frames, 14.0) == ["plateau"]
    for epoch in (15.0, 16.0, 17.0, 18.0):
        assert _standing_at(frames, epoch) == [], epoch
    assert _standing_at(frames, 20.0) == ["plateau"]


def test_what_stands_at_the_end_is_true_of_the_last_five_readings() -> None:
    _, frames = _told(KERAS)
    last_five = [f.primary_metric_value for f in frames[-5:]]
    assert (max(last_five) - min(last_five)) / last_five[0] < 0.01


def test_the_report_lists_the_standing_warning_once_and_no_withdrawal() -> None:
    store, _ = _told(KERAS)
    report = build_markdown("r", store)
    assert report.count(message("warn_plateau", "en")) == 1
    assert message("warn_plateau_cleared", "en") not in report


def test_the_report_does_not_list_a_withdrawn_warning() -> None:
    store, frames = _told(RESNET)
    # Premise: the run did warn, and did withdraw it.
    kinds = [w.kind for f in frames for w in f.warnings]
    assert "overfit" in kinds and "overfit_cleared" in kinds
    report = build_markdown("r", store)
    assert message("warn_overfit", "en") not in report
    assert message("warn_overfit_cleared", "en") not in report
