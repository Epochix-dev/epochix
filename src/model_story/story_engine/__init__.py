from __future__ import annotations

from dataclasses import dataclass, field

from model_story.enums import Grade, Phase, TaskType
from model_story.models import MetaphorCard, MetricEvent, Milestone, StoryFrame
from model_story.story_engine.config_loader import GradeConfig
from model_story.story_engine.grade import compute_grade, is_lower_better
from model_story.story_engine.milestones import MilestoneTracker
from model_story.story_engine.narrator import narrate
from model_story.story_engine.phases import (
    compute_phase,
    estimate_progress,
    relative_improvement,
)
from model_story.story_engine.task_classifier import classify_task, refine_gaze
from model_story.story_engine.warnings import WarningDetector

_PRIMARY_KEY_FOR_TASK: dict[TaskType, str] = {
    TaskType.CLASSIFICATION: "val_accuracy",
    TaskType.DETECTION: "mAP50",
    TaskType.NLP: "perplexity",
    TaskType.BIOMETRIC: "EER",
    TaskType.GAZE: "MAE",
    TaskType.REGRESSION: "MAE",
    TaskType.GENERATIVE: "fid",
    TaskType.CUSTOM: "val_loss",
}


@dataclass
class StoryEngine:
    run_id: str
    task: TaskType | None = None        # None = auto-detect
    primary_metric: str | None = None   # None = inferred from task
    total_epochs: int | None = None
    locale: str = "en"
    grade_config: GradeConfig | None = None  # loaded from .model-story.yaml

    _seen_keys: set[str] = field(default_factory=set, init=False)
    _events_count: int = field(default=0, init=False)
    _task_locked: bool = field(default=False, init=False)
    _baseline: float | None = field(default=None, init=False)
    _prev_frame: StoryFrame | None = field(default=None, init=False)
    _prev_primary: float | None = field(default=None, init=False)
    _milestones: MilestoneTracker | None = field(default=None, init=False)
    _warnings: WarningDetector = field(default_factory=WarningDetector, init=False)
    _metric_history: dict[str, list[float]] = field(default_factory=dict, init=False)

    def _effective_task(self) -> TaskType:
        return self.task or TaskType.CUSTOM

    def _effective_primary_key(self) -> str:
        if self.primary_metric:
            return self.primary_metric
        return _PRIMARY_KEY_FOR_TASK.get(self._effective_task(), "val_loss")

    def process(self, event: MetricEvent) -> StoryFrame | None:
        """Process one MetricEvent and return a StoryFrame (or None if not enough data yet)."""
        self._events_count += 1
        self._seen_keys.add(event.canonical_key)

        # Accumulate metric history
        hist = self._metric_history.setdefault(event.canonical_key, [])
        hist.append(event.value)

        # Auto-detect task after 3 events
        if not self._task_locked and self.task is None and self._events_count >= 3:
            detected = classify_task(self._seen_keys)
            # Refine: MAE < 10 → gaze
            if detected == TaskType.REGRESSION and event.canonical_key == "MAE":
                detected = refine_gaze(detected, event.value)
            self.task = detected
            self._task_locked = True
            self._milestones = MilestoneTracker(run_id=self.run_id, task=self.task)

        if self._events_count < 3:
            return None

        if self._milestones is None:
            self._milestones = MilestoneTracker(
                run_id=self.run_id,
                task=self._effective_task(),
            )

        primary_key = self._effective_primary_key()
        if event.canonical_key != primary_key:
            return None  # only emit frames on primary metric updates

        primary_value = event.value

        if self._baseline is None:
            self._baseline = primary_value

        progress = estimate_progress(
            current_epoch=event.epoch,
            total_epochs=self.total_epochs,
            step=event.step,
        )

        lower_better = is_lower_better(self._effective_task(), self.grade_config)

        phase = compute_phase(
            progress=progress,
            primary_value=primary_value,
            baseline=self._baseline,
            lower_better=lower_better,
        )

        # Honest "advancement" 0–1: the clock when total length is known, else
        # the fraction of achievable metric improvement realised so far. Used
        # for both the progress bar and the maturity signal (NOT a statistical
        # prediction confidence).
        rel = relative_improvement(
            primary_value, self._baseline, lower_better=lower_better,
        )
        advancement = progress if progress is not None else (rel if rel is not None else 0.0)

        grade = compute_grade(
            task=self._effective_task(),
            primary_value=primary_value,
            config=self.grade_config,
        )

        delta = primary_value - self._prev_primary if self._prev_primary is not None else 0.0
        narrative = narrate(
            task=self._effective_task(),
            phase=phase,
            epoch=event.epoch,
            primary_value=primary_value,
            delta=delta,
            run_id=self.run_id,
            locale=self.locale,
        )

        milestones = self._milestones.check(
            epoch=event.epoch,
            seq=event.seq,
            primary_value=primary_value,
            prev_value=self._prev_primary,
        )

        # Gather warning inputs from latest history
        def last(key: str) -> float | None:
            h = self._metric_history.get(key)
            return h[-1] if h else None

        warnings = self._warnings.update(
            epoch=event.epoch,
            train_loss=last("train_loss"),
            val_loss=last("val_loss"),
            primary_value=primary_value,
            lr=last("lr"),
        )

        # Build skill dimensions (radar data)
        skill_dims = self._build_skill_dimensions()

        frame = StoryFrame(
            run_id=self.run_id,
            seq=event.seq,
            epoch=event.epoch,
            progress=advancement,
            phase=phase,
            grade=grade,
            primary_metric_value=primary_value,
            # "confidence" is the run's *advancement/maturity* (0–1), not a
            # prediction-confidence estimate — kept under this field name for
            # storage/back-compat; UI labels it "Maturity".
            confidence=advancement,
            narrative=narrative,
            metaphor_cards=self._build_metaphor_cards(phase, grade),
            skill_dimensions=skill_dims,
            milestones=milestones,
            warnings=warnings,
            task_type=self._effective_task(),
        )

        self._prev_frame = frame
        self._prev_primary = primary_value
        return frame

    def _build_skill_dimensions(self) -> dict[str, float]:
        dims: dict[str, float] = {}
        if self._metric_history.get("accuracy"):
            dims["Accuracy"] = self._metric_history["accuracy"][-1]
        if self._metric_history.get("val_accuracy"):
            dims["Val Accuracy"] = self._metric_history["val_accuracy"][-1]
        if self._metric_history.get("train_loss"):
            # Invert loss for radar (lower is better → show as higher bar)
            loss = self._metric_history["train_loss"][-1]
            dims["Fitting"] = max(0.0, 1.0 - min(loss, 1.0))
        if self._metric_history.get("val_loss"):
            loss = self._metric_history["val_loss"][-1]
            dims["Generalisation"] = max(0.0, 1.0 - min(loss, 1.0))
        return dims

    def _build_metaphor_cards(self, phase: Phase, grade: Grade) -> list[MetaphorCard]:
        return [
            MetaphorCard(
                title="Phase",
                body=phase.value.capitalize(),
                icon="zap",
            ),
            MetaphorCard(
                title="Grade",
                body=grade.value,
                icon="star",
            ),
        ]

    def finalize(self, last_seq: int, last_epoch: float | None) -> list[Milestone]:
        """Return final milestones. Call when training stream ends."""
        if self._milestones is None:
            return []
        return self._milestones.finalize(last_seq, last_epoch)
