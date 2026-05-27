"""Story engine unit tests."""
from __future__ import annotations

from datetime import datetime, timezone

from epochix.enums import Grade, Phase, TaskType
from epochix.models import MetricEvent
from epochix.story_engine import StoryEngine
from epochix.story_engine.grade import compute_grade
from epochix.story_engine.phases import compute_phase
from epochix.story_engine.task_classifier import classify_task


def _event(
    canonical_key: str,
    value: float,
    epoch: float | None = None,
    seq: int = 0,
    run_id: str = "test-run",
) -> MetricEvent:
    return MetricEvent(
        run_id=run_id,
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=epoch,
        canonical_key=canonical_key,
        raw_key=canonical_key,
        value=value,
    )


class TestPhaseDetector:
    def test_awakening_at_start(self) -> None:
        assert compute_phase(0.05, 0.1, 0.1) == Phase.AWAKENING

    def test_learning_early(self) -> None:
        assert compute_phase(0.20, 0.3, 0.0) == Phase.LEARNING

    def test_understanding_midway(self) -> None:
        assert compute_phase(0.55, 0.80, 0.0) == Phase.UNDERSTANDING

    def test_mastering_late(self) -> None:
        assert compute_phase(0.85, 0.92, 0.0) == Phase.MASTERING

    def test_polishing_at_end(self) -> None:
        assert compute_phase(0.98, 0.98, 0.0) == Phase.POLISHING

    def test_lower_better_advances_on_loss_drop(self) -> None:
        # A loss falling from 2.0 → 0.2 with unknown total length should NOT be
        # stuck in AWAKENING — relative improvement drives advancement.
        assert compute_phase(None, 0.2, 2.0, lower_better=True) != Phase.AWAKENING

    def test_lower_better_early_is_awakening(self) -> None:
        # Barely any improvement yet → still awakening.
        assert compute_phase(None, 1.95, 2.0, lower_better=True) == Phase.AWAKENING


class TestGrader:
    def test_classification_high_acc(self) -> None:
        grade = compute_grade(TaskType.CLASSIFICATION, 0.96)
        assert grade == Grade.A_PLUS

    def test_classification_low_acc(self) -> None:
        grade = compute_grade(TaskType.CLASSIFICATION, 0.30)
        assert grade == Grade.F

    def test_biometric_low_eer(self) -> None:
        grade = compute_grade(TaskType.BIOMETRIC, 0.008)
        assert grade == Grade.A_PLUS

    def test_biometric_high_eer(self) -> None:
        # EER=0.35 is below the D threshold (0.40), so grade is D
        assert compute_grade(TaskType.BIOMETRIC, 0.35) == Grade.D
        # EER > 0.40 falls through to F
        assert compute_grade(TaskType.BIOMETRIC, 0.45) == Grade.F


class TestTaskClassifier:
    def test_biometric_from_eer(self) -> None:
        assert classify_task({"EER", "train_loss"}) == TaskType.BIOMETRIC

    def test_detection_from_map(self) -> None:
        assert classify_task({"mAP50", "box_loss"}) == TaskType.DETECTION

    def test_nlp_from_perplexity(self) -> None:
        assert classify_task({"perplexity", "train_loss"}) == TaskType.NLP

    def test_classification_fallback(self) -> None:
        assert classify_task({"accuracy", "val_accuracy", "train_loss"}) == TaskType.CLASSIFICATION

    def test_custom_on_unknown(self) -> None:
        assert classify_task({"some_custom_metric"}) == TaskType.CUSTOM


class TestStoryEngine:
    def test_returns_none_before_three_events(self) -> None:
        engine = StoryEngine(run_id="test")
        e1 = _event("accuracy", 0.5, epoch=1.0, seq=1)
        e2 = _event("accuracy", 0.55, epoch=2.0, seq=2)
        assert engine.process(e1) is None
        assert engine.process(e2) is None

    def test_emits_frame_after_sufficient_data(self) -> None:
        engine = StoryEngine(run_id="test", task=TaskType.CLASSIFICATION)
        for i in range(5):
            e = _event("val_accuracy", 0.4 + i * 0.05, epoch=float(i + 1), seq=i)
            frame = engine.process(e)
        assert frame is not None
        assert frame.grade in list(Grade)
        assert frame.phase in list(Phase)

    def test_narrative_is_deterministic(self) -> None:
        """Same run_id + same inputs → same narrative."""
        def run(run_id: str) -> str:
            engine = StoryEngine(run_id=run_id, task=TaskType.CLASSIFICATION)
            frame = None
            for i in range(5):
                ev = _event("val_accuracy", 0.5 + i * 0.05, epoch=float(i + 1), seq=i)
                frame = engine.process(ev)
            assert frame is not None
            return frame.narrative

        n1 = run("fixed-id")
        n2 = run("fixed-id")
        assert n1 == n2

    def test_biometric_task_detection(self) -> None:
        engine = StoryEngine(run_id="bio-test")
        events = [
            _event("EER", 0.35, epoch=1.0, seq=0),
            _event("train_loss", 1.4, epoch=1.0, seq=1),
            _event("EER", 0.28, epoch=2.0, seq=2),
            _event("EER", 0.22, epoch=3.0, seq=3),
            _event("EER", 0.18, epoch=4.0, seq=4),
        ]
        frame = None
        for e in events:
            f = engine.process(e)
            if f is not None:
                frame = f
        assert frame is not None
        assert engine.task == TaskType.BIOMETRIC
