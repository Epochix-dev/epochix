"""Unit tests for model_story.models and model_story.enums."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from model_story.enums import Grade, Phase, TaskType
from model_story.models import (
    MetaphorCard,
    MetricEvent,
    Milestone,
    RawLogLine,
    RawMetric,
    Run,
    StoryFrame,
    Warning,
    WSMessage,
)

# ── Enums ─────────────────────────────────────────────────────────────────────

class TestEnums:
    def test_phase_values(self) -> None:
        assert Phase.AWAKENING.value == "awakening"
        assert Phase.POLISHING.value == "polishing"
        assert len(Phase) == 5

    def test_grade_values(self) -> None:
        assert Grade.A_PLUS.value == "A+"
        assert Grade.F.value == "F"
        assert Grade.INCOMPLETE.value == "I"
        assert len(Grade) == 12

    def test_task_type_values(self) -> None:
        assert TaskType.CLASSIFICATION.value == "classification"
        assert TaskType.DETECTION.value == "detection"
        assert TaskType.NLP.value == "nlp"
        assert len(TaskType) >= 7

    def test_enum_string_comparison(self) -> None:
        # Enums inherit from str — can be compared to strings
        assert Phase.AWAKENING == "awakening"
        assert Grade.A_PLUS == "A+"
        assert TaskType.NLP == "nlp"


# ── RawLogLine ────────────────────────────────────────────────────────────────

class TestRawLogLine:
    def test_valid(self) -> None:
        now = datetime.now(timezone.utc)
        line = RawLogLine(seq=1, timestamp=now, source="stdin", text="hello")
        assert line.seq == 1
        assert line.source == "stdin"

    def test_invalid_source(self) -> None:
        with pytest.raises(ValidationError):
            RawLogLine(
                seq=1, timestamp=datetime.now(timezone.utc),
                source="invalid",  # type: ignore[arg-type]
                text="x",
            )


# ── RawMetric ─────────────────────────────────────────────────────────────────

class TestRawMetric:
    def test_valid_float(self) -> None:
        m = RawMetric(seq=1, key="loss", value=0.5, parser_name="pl", confidence=0.9)
        assert m.value == 0.5
        assert m.epoch is None
        assert m.step is None

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RawMetric(seq=1, key="loss", value=0.5, parser_name="pl", confidence=1.5)
        with pytest.raises(ValidationError):
            RawMetric(seq=1, key="loss", value=0.5, parser_name="pl", confidence=-0.1)

    def test_string_value_allowed(self) -> None:
        m = RawMetric(seq=1, key="status", value="ok", parser_name="pl", confidence=0.5)
        assert m.value == "ok"


# ── MetricEvent ───────────────────────────────────────────────────────────────

class TestMetricEvent:
    def test_valid(self) -> None:
        e = MetricEvent(
            run_id="r1", seq=1, timestamp=datetime.now(timezone.utc),
            canonical_key="val_accuracy", raw_key="acc", value=0.85,
        )
        assert e.value == 0.85
        assert e.unit is None
        assert e.task_hint is None

    def test_with_task_hint(self) -> None:
        e = MetricEvent(
            run_id="r1", seq=1, timestamp=datetime.now(timezone.utc),
            canonical_key="mAP50", raw_key="map50", value=0.72,
            task_hint=TaskType.DETECTION,
        )
        assert e.task_hint == TaskType.DETECTION


# ── StoryFrame ────────────────────────────────────────────────────────────────

class TestStoryFrame:
    def _frame(self, **overrides: object) -> StoryFrame:
        defaults: dict[str, object] = {
            "run_id": "r1", "seq": 1, "epoch": 5.0,
            "progress": 0.5, "phase": Phase.LEARNING, "grade": Grade.B,
            "primary_metric_value": 0.75, "confidence": 0.8,
            "narrative": "Learning.", "task_type": TaskType.CLASSIFICATION,
        }
        defaults.update(overrides)
        return StoryFrame(**defaults)  # type: ignore[arg-type]

    def test_valid(self) -> None:
        f = self._frame()
        assert f.progress == 0.5
        assert f.grade == Grade.B
        assert f.metaphor_cards == []
        assert f.skill_dimensions == {}

    def test_progress_bounds(self) -> None:
        with pytest.raises(ValidationError):
            self._frame(progress=1.1)
        with pytest.raises(ValidationError):
            self._frame(progress=-0.1)

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            self._frame(confidence=2.0)

    def test_with_metaphor_cards(self) -> None:
        card = MetaphorCard(title="Awakening", body="First steps.", icon="🌱")
        f = self._frame(metaphor_cards=[card])
        assert len(f.metaphor_cards) == 1
        assert f.metaphor_cards[0].title == "Awakening"

    def test_with_milestone(self) -> None:
        ms = Milestone(run_id="r1", seq=5, kind="best_val_accuracy",
                       epoch=5.0, value=0.9, message="New best!")
        f = self._frame(milestones=[ms])
        assert f.milestones[0].kind == "best_val_accuracy"

    def test_with_warning(self) -> None:
        w = Warning(kind="plateau", epoch=10.0, message="Plateau detected.")
        f = self._frame(warnings=[w])
        assert f.warnings[0].kind == "plateau"


# ── Run ───────────────────────────────────────────────────────────────────────

class TestRun:
    def _run(self, **overrides: object) -> Run:
        defaults: dict[str, object] = {
            "id": "01JABCDEF", "task_type": TaskType.CLASSIFICATION,
            "started_at": datetime.now(timezone.utc),
            "primary_metric": "val_accuracy", "parser_used": "pytorch_lightning",
        }
        defaults.update(overrides)
        return Run(**defaults)  # type: ignore[arg-type]

    def test_valid(self) -> None:
        r = self._run()
        assert r.id == "01JABCDEF"
        assert r.final_grade is None
        assert r.config == {}

    def test_with_grade(self) -> None:
        r = self._run(final_grade=Grade.A)
        assert r.final_grade == Grade.A

    def test_optional_fields_default(self) -> None:
        r = self._run()
        assert r.name is None
        assert r.finished_at is None
        assert r.framework_detected is None
        assert r.total_epochs_est is None
        assert r.story_summary is None


# ── WSMessage ─────────────────────────────────────────────────────────────────

class TestWSMessage:
    def test_story_frame(self) -> None:
        msg = WSMessage(
            type="story_frame", run_id="r1", seq=1,
            ts=datetime.now(timezone.utc),
        )
        assert msg.v == 1
        assert msg.type == "story_frame"
        assert msg.payload == {}

    def test_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            WSMessage(
                type="unknown_type",  # type: ignore[arg-type]
                run_id="r1", seq=1, ts=datetime.now(timezone.utc),
            )

    def test_milestone_with_payload(self) -> None:
        msg = WSMessage(
            type="milestone", run_id="r1", seq=5,
            ts=datetime.now(timezone.utc),
            payload={"kind": "best_val_accuracy", "message": "New best!"},
        )
        assert msg.payload["kind"] == "best_val_accuracy"


# ── Warning validation ────────────────────────────────────────────────────────

class TestWarning:
    def test_valid_kinds(self) -> None:
        for kind in ("overfit", "plateau", "divergence", "lr_drop"):
            w = Warning(kind=kind, message="msg")  # type: ignore[arg-type]
            assert w.kind == kind

    def test_invalid_kind(self) -> None:
        with pytest.raises(ValidationError):
            Warning(kind="unknown", message="msg")  # type: ignore[arg-type]


# ── Milestone ─────────────────────────────────────────────────────────────────

class TestMilestone:
    def test_minimal(self) -> None:
        ms = Milestone(run_id="r1", seq=1, kind="first_metric", message="First!")
        assert ms.epoch is None
        assert ms.value is None

    def test_full(self) -> None:
        ms = Milestone(run_id="r1", seq=10, kind="best_val_accuracy",
                       epoch=10.0, value=0.92, message="New best accuracy!")
        assert ms.value == 0.92
