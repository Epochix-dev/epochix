"""A run that ends before the warmup completes must still tell its story.

The story engine buffers events until three have arrived, so the task
classifier has something to work with. Nothing emptied that buffer when the run
ended, so a log that never reached three metric events produced no frames, no
grade and no summary — silently, with a successful exit code.

That is the ordinary shape of a classical-ML script: fit once, print a score.
It is also what cross-validation reduces to once folds are aggregated into
their mean, so #64 depended on this.
"""

from __future__ import annotations

from datetime import datetime, timezone

from epochix.enums import Grade, TaskType
from epochix.models import MetricEvent
from epochix.story_engine import StoryEngine


def _event(key: str, value: float, seq: int) -> MetricEvent:
    return MetricEvent(
        run_id="r",
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=None,
        canonical_key=key,
        raw_key=key,
        value=value,
    )


class TestWarmupFlush:
    def test_a_single_event_still_produces_a_frame(self) -> None:
        eng = StoryEngine(run_id="r")
        assert eng.process_all(_event("val_accuracy", 0.982, 1)) == []
        frames = eng.flush_warmup()
        assert len(frames) == 1
        assert frames[0].primary_metric_value == 0.982

    def test_two_events_produce_frames(self) -> None:
        eng = StoryEngine(run_id="r")
        eng.process_all(_event("val_accuracy", 0.90, 1))
        eng.process_all(_event("f1", 0.88, 2))
        assert eng.flush_warmup()

    def test_the_task_is_still_classified(self) -> None:
        """Fewer events make detection less certain, not wrong."""
        eng = StoryEngine(run_id="r")
        eng.process_all(_event("val_accuracy", 0.982, 1))
        eng.flush_warmup()
        assert eng.task is TaskType.CLASSIFICATION

    def test_the_grade_is_real_when_the_metric_has_a_scale(self) -> None:
        eng = StoryEngine(run_id="r")
        eng.process_all(_event("val_accuracy", 0.982, 1))
        frames = eng.flush_warmup()
        assert frames[0].grade is Grade.A_PLUS

    def test_flushing_twice_does_not_duplicate(self) -> None:
        eng = StoryEngine(run_id="r")
        eng.process_all(_event("val_accuracy", 0.982, 1))
        assert len(eng.flush_warmup()) == 1
        assert eng.flush_warmup() == []

    def test_a_run_that_warmed_up_normally_flushes_nothing(self) -> None:
        eng = StoryEngine(run_id="r")
        for seq in range(1, 5):
            eng.process_all(_event("val_accuracy", 0.5 + seq * 0.1, seq))
        assert eng.flush_warmup() == []
