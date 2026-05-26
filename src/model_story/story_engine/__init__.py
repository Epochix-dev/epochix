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
        """Per-task radar axes, populated from whatever the parser captured.

        The axes are chosen so every supported task type gets a meaningful
        radar — not just classification. All values are clamped to [0, 1] so
        the radar render is uniform; lower-is-better metrics are inverted.
        """
        h = self._metric_history

        def _last(key: str) -> float | None:
            seq = h.get(key)
            return seq[-1] if seq else None

        def _inv(v: float | None, *, scale: float = 1.0) -> float | None:
            """Invert a lower-is-better metric into a [0,1] "skill" score."""
            return None if v is None else max(0.0, 1.0 - min(v / scale, 1.0))

        dims: dict[str, float] = {}
        task = self._effective_task()

        def _add(key: str, value: float | None) -> None:
            if value is not None:
                dims[key] = value

        if task == TaskType.DETECTION:
            # YOLO / object-detection axes — every one is reported by the
            # Ultralytics parser, so the radar is full on real detection runs.
            _add("mAP50", _last("mAP50"))
            _add("mAP50-95", _last("mAP"))
            _add("Precision", _last("precision"))
            _add("Recall", _last("recall"))
            # Localisation quality: low box_loss → tight boxes.
            _add("Localisation", _inv(_last("box_loss"), scale=4.0))
        elif task == TaskType.BIOMETRIC:
            _add("1 − EER", _inv(_last("EER"), scale=0.5))
            _add("TAR", _last("TAR"))
            _add("TAR@FAR=1e-3", _last("TAR_at_FAR_0_001"))
        elif task == TaskType.GAZE:
            _add("1 − MAE", _inv(_last("MAE"), scale=30.0))
            _add("1 − RMSE", _inv(_last("RMSE"), scale=30.0))
        elif task == TaskType.NLP:
            _add("1 − Perplexity", _inv(_last("perplexity"), scale=200.0))
            _add("BLEU", _last("bleu"))
            _add("ROUGE", _last("rouge"))
        elif task == TaskType.REGRESSION:
            _add("1 − MAE", _inv(_last("MAE"), scale=2.0))
            _add("1 − RMSE", _inv(_last("RMSE"), scale=2.0))

        # Classification axes — also act as the universal fallback so any run
        # that happens to log these gets them on the radar regardless of task.
        _add("Accuracy", _last("accuracy"))
        _add("Val Accuracy", _last("val_accuracy"))
        _add("Fitting", _inv(_last("train_loss")))
        _add("Generalisation", _inv(_last("val_loss")))

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
