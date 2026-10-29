"""A metric nothing says the direction of is not graded on improvement.

Grading on improvement needs to know which way is better. For a CUSTOM run's
story metric whose name pins no direction, with no `.epochix.yaml` to say,
the engine used `bool(None)` — higher is better — and graded on that. The
recorded CatBoost run whose unnamed eval metric is AUC 1.0 every round came
out D ("essentially flat"), in Awakening, told "an opening reading" at its
thirtieth: a verdict on a run nobody can judge from its log. Its letter is
now "I", the one the engine gives a reading it cannot judge.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from epochix.enums import Grade, TaskType
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import MetricEvent, StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import StoryEngine
from epochix.story_engine.config_loader import GradeConfig
from epochix.story_engine.grade import metric_lower_better

LOGS = Path(__file__).resolve().parents[1] / "fixtures" / "logs"


def _frames(key: str, values: list[float], config: GradeConfig | None = None) -> list[StoryFrame]:
    engine = StoryEngine(run_id="r", task=TaskType.CUSTOM, grade_config=config)
    frames: list[StoryFrame] = []
    for seq, value in enumerate(values, start=1):
        event = MetricEvent(
            run_id="r",
            seq=seq,
            timestamp=datetime.now(tz=timezone.utc),
            epoch=float(seq),
            canonical_key=key,
            raw_key=key,
            value=value,
        )
        frames += engine.process_all(event)
    assert frames, f"no frame emitted for {key}"
    assert {f.primary_metric for f in frames} == {key}
    return frames


def test_the_name_used_here_pins_no_direction() -> None:
    assert metric_lower_better("val_metric") is None
    assert metric_lower_better("widget_count") is None


def test_the_real_flat_catboost_run_is_not_graded() -> None:
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester("r", str(LOGS / "catboost_real_flat_auc.log")),
            run_id="r",
            store=store,
            hub=Hub(),
        )
    )
    frames = store.get_story_frames("r")
    assert len(frames) == 30
    assert {(f.grade, f.grade_basis) for f in frames} == {(Grade.INCOMPLETE, None)}
    assert not any("opening" in f.narrative or "beginning" in f.narrative for f in frames)


def test_a_moving_metric_with_no_direction_is_not_graded_either() -> None:
    # Which way it moved says nothing about whether that is better.
    for values in ([0.2, 0.4, 0.6, 0.8], [0.8, 0.6, 0.4, 0.2]):
        frames = _frames("widget_count", values)
        assert {f.grade for f in frames} == {Grade.INCOMPLETE}, values
        assert {f.grade_basis for f in frames} == {None}


def test_a_thresholds_file_that_states_the_direction_is_graded() -> None:
    falling = _frames(
        "widget_count", [0.8, 0.6, 0.4, 0.2], GradeConfig(lower_better_override={"custom": True})
    )
    assert falling[-1].grade_basis == "improvement"
    assert falling[-1].grade is not Grade.INCOMPLETE


def test_a_name_that_states_its_direction_is_still_graded() -> None:
    # val_score is pinned higher-is-better: a rising one is graded on improvement.
    frames = _frames("val_score", [0.5, 0.6, 0.7, 0.8])
    assert frames[-1].grade_basis == "improvement"
    assert frames[-1].grade is not Grade.INCOMPLETE
