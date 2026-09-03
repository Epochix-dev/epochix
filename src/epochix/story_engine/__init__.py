from __future__ import annotations

import math
from dataclasses import dataclass, field

from epochix.enums import Grade, Phase, TaskType
from epochix.models import MetaphorCard, MetricEvent, Milestone, StoryFrame, Warning
from epochix.normalizer.canonical_keys import canonicalize_key
from epochix.story_engine.config_loader import GradeConfig
from epochix.story_engine.grade import (
    compute_grade,
    grade_by_trajectory,
    has_absolute_scale,
    impossible_reason,
    is_lower_better,
    metric_lower_better,
)
from epochix.story_engine.milestones import MilestoneTracker
from epochix.story_engine.narrator import (
    narrate,
    narrate_diverged,
    narrate_past_peak,
    narrate_single_reading,
    narrate_stalled,
)
from epochix.story_engine.phases import (
    compute_phase,
    estimate_progress,
    relative_improvement,
)
from epochix.story_engine.task_classifier import classify_task, refine_gaze
from epochix.story_engine.warnings import WarningDetector

# Ordered candidate primary metrics per task (best first). The engine drives
# the story off the highest-priority one that is actually logged, so a run that
# reports a valid alternative for its task — RMSE instead of MAE, mAP instead of
# mAP50, bleu instead of perplexity — still produces frames instead of matching
# nothing. The first entry doubles as the default when none has been seen yet.
_PREFERRED_KEYS_FOR_TASK: dict[TaskType, tuple[str, ...]] = {
    # A metric only reaches the story if it is listed here. Recognising an
    # alias is not enough: MAPE parsed correctly yet the run still graded on
    # train_loss, so an improving and a worsening run scored the same.
    TaskType.CLASSIFICATION: (
        "val_accuracy",
        "accuracy",
        "AUC",
        "val_AUC",
        "PR_AUC",
        "f1",
        "val_f1",
        "top5_accuracy",
        "balanced_accuracy",
        "MCC",
        # Detected the task, so it must be able to tell its story: a key
        # that classifies a run and is then unreadable leaves the run with
        # no frames, no grade and exit 0.
        "kappa",
        # Last resorts. Gradient boosting classifiers print their objective and
        # nothing else by default, so without these the task was detected as
        # classification and then no preferred key had ever been logged — the
        # primary metric fell back to val_accuracy, matched no event, and the
        # run produced no story at all. They are off-scale (see below) and so
        # grade on improvement, not against accuracy bands.
        "val_log_loss",
        "log_loss",
        "val_error_rate",
        "error_rate",
    ),
    TaskType.DETECTION: (
        "mAP50",
        "mAP",
        "mAP75",
        # Detected the task, so it must be able to tell its story: a key
        # that classifies a run and is then unreadable leaves the run with
        # no frames, no grade and exit 0.
        "box_loss",
        "cls_loss",
        # Last resorts, exactly as classification carries them. The task is chosen
        # from the metric NAMES in the log, and several of those names are losses
        # or appear long before the headline metric is first computed — YOLO prints
        # box_loss and cls_loss every epoch and mAP only at validation. Without a
        # fallback the primary key never arrived, so the run produced no frames, no
        # grade and no summary: "Grade: N/A" and exit 0. Off-scale, so they grade
        # on improvement rather than against the task's bands.
        "val_loss",
        "loss",
        "train_loss",
    ),
    TaskType.NLP: (
        "perplexity",
        "bleu",
        "rouge",
        "WER",
        "CER",
        "BPC",
        # Last resorts, exactly as classification carries them. The task is chosen
        # from the metric NAMES in the log, and several of those names are losses
        # or appear long before the headline metric is first computed — YOLO prints
        # box_loss and cls_loss every epoch and mAP only at validation. Without a
        # fallback the primary key never arrived, so the run produced no frames, no
        # grade and no summary: "Grade: N/A" and exit 0. Off-scale, so they grade
        # on improvement rather than against the task's bands.
        "val_loss",
        "loss",
        "train_loss",
    ),
    TaskType.BIOMETRIC: (
        "EER",
        "TAR",
        # Detected the task, so it must be able to tell its story: a key
        # that classifies a run and is then unreadable leaves the run with
        # no frames, no grade and exit 0.
        "TAR_at_FAR_0_001",
        "FAR",
        # Last resorts, exactly as classification carries them. The task is chosen
        # from the metric NAMES in the log, and several of those names are losses
        # or appear long before the headline metric is first computed — YOLO prints
        # box_loss and cls_loss every epoch and mAP only at validation. Without a
        # fallback the primary key never arrived, so the run produced no frames, no
        # grade and no summary: "Grade: N/A" and exit 0. Off-scale, so they grade
        # on improvement rather than against the task's bands.
        "val_loss",
        "loss",
        "train_loss",
    ),
    TaskType.GAZE: ("val_MAE", "val_RMSE", "MAE", "RMSE"),
    TaskType.SEGMENTATION: (
        "mIoU",
        "IoU",
        "Dice",
        "pixel_accuracy",
        # Last resorts, exactly as classification carries them. The task is chosen
        # from the metric NAMES in the log, and several of those names are losses
        # or appear long before the headline metric is first computed — YOLO prints
        # box_loss and cls_loss every epoch and mAP only at validation. Without a
        # fallback the primary key never arrived, so the run produced no frames, no
        # grade and no summary: "Grade: N/A" and exit 0. Off-scale, so they grade
        # on improvement rather than against the task's bands.
        "val_loss",
        "loss",
        "train_loss",
    ),
    # R² first, because it is the only one of these that means anything on its
    # own: MAE and RMSE are in the target's units, so "MAE 9.83" is excellent
    # for house prices and terrible for a probability. Then validation before
    # train — boosting prints both, and grading a run on its TRAINING error
    # rewards exactly the overfitting the story is meant to call out.
    TaskType.REGRESSION: (
        "val_R2",
        "R2",
        "val_MAE",
        "val_RMSE",
        "val_MSE",
        "val_MAPE",
        "MAE",
        "RMSE",
        "MSE",
        "MAPE",
        # Detected the task, so it must be able to tell its story: a key
        # that classifies a run and is then unreadable leaves the run with
        # no frames, no grade and exit 0.
        "MedAE",
        "RMSLE",
        "explained_variance",
    ),
    TaskType.GENERATIVE: (
        "fid",
        "is_score",
        "PSNR",
        "SSIM",
        "LPIPS",
        # Last resorts, exactly as classification carries them. The task is chosen
        # from the metric NAMES in the log, and several of those names are losses
        # or appear long before the headline metric is first computed — YOLO prints
        # box_loss and cls_loss every epoch and mAP only at validation. Without a
        # fallback the primary key never arrived, so the run produced no frames, no
        # grade and no summary: "Grade: N/A" and exit 0. Off-scale, so they grade
        # on improvement rather than against the task's bands.
        "val_loss",
        "loss",
        "train_loss",
    ),
    # "custom" last, so a run whose only metric has a name we do not recognise
    # still tells a story. Without it the primary key stayed val_loss, matched
    # no event, and a log reporting nothing but an unnamed score — scikit-learn's
    # own `cross_val_score` verbose output is exactly that — produced no frames,
    # no grade and no summary at all.
    TaskType.CUSTOM: ("val_loss", "train_loss", "custom"),
}

# A run is "stalled" when, after this many epochs of the primary metric, it has
# realised less than this fraction of its achievable improvement. Deliberately
# conservative: we would rather stay quiet than wrongly call a slow-but-real
# improvement a failure.

# A run is 'past peak' when the primary metric has fallen this far (relative)
# below its own best. Above noise, below the point of nagging about jitter.
_PAST_PEAK_REL_DROP = 0.01

_STALL_MIN_EPOCHS = 3
_STALL_REL_IMPROVEMENT = 0.03

# Keys the task's ABSOLUTE grade bands were written for. Everything else is
# graded on improvement instead (see the off_scale branch below).
#
# Defaults to just the first preferred key.
#
# Regression lists only the R² forms. Its task bands are MAE bands, and MAE
# carries the target's units, so they graded a model with R² 0.996 as F purely
# because its targets were large. R² brings its own scale (see
# _METRIC_THRESHOLDS); MAE and RMSE are now graded on improvement, which is the
# only honest reading of an error whose units are unknown.
#
# Gaze keeps MAE, and the difference is not arbitrary: gaze MAE is an angle in
# degrees. 0.5° is genuinely excellent and 20° genuinely poor whatever the
# dataset, so those bands mean something a generic MAE band cannot.
_ON_SCALE_KEYS: dict[TaskType, frozenset[str]] = {
    TaskType.REGRESSION: frozenset({"val_R2", "R2"}),
    TaskType.GAZE: frozenset({"val_MAE", "MAE"}),
    # The classification bands ARE accuracy bands, and accuracy means the same
    # thing whichever split it came from. Only val_accuracy was listed, so a
    # run reporting plain `accuracy` was graded on improvement — and with a
    # single reading (a cross-validation mean, say) that left it ungraded
    # entirely, despite 90.5% being a perfectly gradeable number.
    TaskType.CLASSIFICATION: frozenset({"val_accuracy", "accuracy"}),
}

_PRIMARY_KEY_FOR_TASK: dict[TaskType, str] = {
    task: keys[0] for task, keys in _PREFERRED_KEYS_FOR_TASK.items()
}


@dataclass
class StoryEngine:
    run_id: str
    task: TaskType | None = None  # None = auto-detect
    primary_metric: str | None = None  # None = inferred from task
    total_epochs: int | None = None
    locale: str = "en"
    grade_config: GradeConfig | None = None  # loaded from .epochix.yaml

    _seen_keys: set[str] = field(default_factory=set, init=False)
    # Canonicalising throws away exactly what tells a gaze run apart: both
    # `gaze_mae` and a plain `mae` arrive as MAE. Keep the originals.
    _seen_raw_keys: set[str] = field(default_factory=set, init=False)
    _events_count: int = field(default=0, init=False)
    _task_locked: bool = field(default=False, init=False)
    _baseline: float | None = field(default=None, init=False)
    _best_primary: float | None = field(default=None, init=False)
    _best_epoch: float | None = field(default=None, init=False)
    _primary_key_used: str | None = field(default=None, init=False)
    _prev_frame: StoryFrame | None = field(default=None, init=False)
    _prev_primary: float | None = field(default=None, init=False)
    _milestones: MilestoneTracker | None = field(default=None, init=False)
    _warnings: WarningDetector = field(default_factory=WarningDetector, init=False)
    _metric_history: dict[str, list[float]] = field(default_factory=dict, init=False)
    # Events seen during the task-detection warmup (before frames start emitting)
    # are buffered here and replayed once emission begins, so early epochs aren't
    # silently dropped from the story (grade-arc chart / stat chip).
    _warmup: list[MetricEvent] = field(default_factory=list, init=False)
    _started: bool = field(default=False, init=False)
    # (metric key, epoch) of the first non-numeric reading the log reported.
    # A MetricEvent's value is a FiniteFloat, so a NaN can never travel as one
    # — the pipeline hands it over here instead.
    _non_finite: tuple[str, float | None] | None = field(default=None, init=False)

    def _effective_task(self) -> TaskType:
        return self.task or TaskType.CUSTOM

    def _effective_primary_key(self) -> str:
        # Canonicalise a caller-supplied primary_metric: metric events are
        # stored under canonical keys (e.g. MAE), so a raw name like
        # "val_mae_cm" must be mapped through the same normalizer or it would
        # never match an event and no story frames would ever emit.
        if self.primary_metric:
            return canonicalize_key(self.primary_metric)
        task = self._effective_task()
        # Prefer the highest-priority candidate that has actually been logged,
        # so an alternative-but-valid metric (RMSE vs MAE, mAP vs mAP50) drives
        # the story instead of matching nothing. Fall back to the default when
        # none has appeared yet.
        for key in _PREFERRED_KEYS_FOR_TASK.get(task, ()):
            if key in self._metric_history:
                return key
        return _PRIMARY_KEY_FOR_TASK.get(task, "val_loss")

    def process(self, event: MetricEvent) -> StoryFrame | None:
        """Process one MetricEvent, returning the latest StoryFrame (or None).

        Thin back-compat wrapper over :meth:`process_all`; when a warmup backfill
        emits several frames at once this returns the last one. Callers that must
        persist every frame (the pipeline) should use :meth:`process_all`.
        """
        frames = self.process_all(event)
        return frames[-1] if frames else None

    def process_all(self, event: MetricEvent) -> list[StoryFrame]:
        """Process one MetricEvent and return every StoryFrame it produces.

        Usually 0 or 1 frame. The exception is the moment the task-detection
        warmup ends: the buffered early events are replayed so the first epoch(s)
        aren't dropped from the story, which can yield several frames at once.
        """
        self._events_count += 1
        self._seen_keys.add(event.canonical_key)
        if event.raw_key:
            self._seen_raw_keys.add(event.raw_key)

        # Accumulate metric history
        hist = self._metric_history.setdefault(event.canonical_key, [])
        hist.append(event.value)

        # Auto-detect task once ≥3 events are in. Keep re-classifying while the
        # result is still CUSTOM instead of locking at exactly event 3 — a
        # signal metric (e.g. MAE) can arrive after noise keys (param counts
        # parsed as `custom`, or metric ordering) have already filled the first
        # three events. We lock only once a *definite* (non-custom) task emerges.
        if not self._task_locked and self.task is None and self._events_count >= 3:
            detected = classify_task(self._seen_keys)
            if detected != TaskType.CUSTOM:
                if detected == TaskType.REGRESSION:
                    # val_MAE too: a boosting run reports only its validation
                    # error, so keying on "MAE" alone never refined those.
                    mae_hist = self._metric_history.get("val_MAE") or self._metric_history.get(
                        "MAE"
                    )
                    if mae_hist:
                        detected = refine_gaze(detected, mae_hist[-1], self._seen_raw_keys)
                self.task = detected
                self._task_locked = True
                self._milestones = MilestoneTracker(run_id=self.run_id, task=self.task)

        # Warmup: buffer events until the task-detection window (≥3 events) is
        # satisfied, then start emitting. On the first emit, replay the buffered
        # events so early primary-metric epochs produce frames too (previously
        # anything logged in the first <3 events was lost from the story).
        if not self._started:
            self._warmup.append(event)
            if self._events_count < 3:
                return []
            self._started = True
            self._ensure_milestones()
            frames: list[StoryFrame] = []
            for buffered in self._warmup:
                f = self._emit(buffered)
                if f is not None:
                    frames.append(f)
            self._warmup = []
            return frames

        self._ensure_milestones()
        f = self._emit(event)
        return [f] if f is not None else []

    def flush_warmup(self) -> list[StoryFrame]:
        """Emit buffered events when the run ends before warmup completes.

        The buffer exists so the task classifier has three events to work with
        before anything is narrated. Nothing used to empty it, so a log that
        never reached three metric events produced no frames, no grade and no
        summary — silently, with a successful exit code. That is the ordinary
        shape of a classical-ML script: fit once, print one or two scores.

        Task detection runs here on whatever did arrive. Fewer events make it
        less certain, not wrong: it either recognises a metric or answers
        CUSTOM, and CUSTOM is honest where a guess would not be.
        """
        if self._started or not self._warmup:
            return []

        if self.task is None:
            detected = classify_task(self._seen_keys)
            if detected != TaskType.CUSTOM:
                if detected == TaskType.REGRESSION:
                    mae_hist = self._metric_history.get("val_MAE") or self._metric_history.get(
                        "MAE"
                    )
                    if mae_hist:
                        detected = refine_gaze(detected, mae_hist[-1], self._seen_raw_keys)
                self.task = detected
                self._task_locked = True

        self._started = True
        self._ensure_milestones()
        frames: list[StoryFrame] = []
        for buffered in self._warmup:
            frame = self._emit(buffered)
            if frame is not None:
                frames.append(frame)
        self._warmup = []
        return frames

    def note_non_finite(self, key: str, epoch: float | None) -> None:
        """Record that the log reported a non-numeric value (NaN/inf) for *key*.

        `MetricEvent.value` is a ``FiniteFloat`` on purpose — it is what keeps
        `--json` and the embedded HTML run data valid, since ``NaN`` is not
        legal JSON. So a diverged reading cannot reach the engine as an event,
        and the pipeline reports it through here instead. Only the FIRST one is
        kept: the epoch it broke at is the useful fact, and a diverged run
        usually prints hundreds of them afterwards.
        """
        if self._non_finite is None:
            self._non_finite = (key, epoch)

    def flush_divergence(self, last_seq: int) -> StoryFrame | None:
        """Terminal frame for a run whose metric stopped being a number.

        Without it the story stopped at the last finite epoch and the run kept
        the grade it had earned before it blew up: a model whose loss went to
        NaN at epoch 4 was reported as "Grade: B+, the model makes steady
        progress", with no warning anywhere. `loss: nan` is the plainest
        failure signal a training log has.

        The frame carries the last REAL epoch and the last REAL value, because
        `StoryFrame` has nowhere to put "no reading" — `primary_metric_value`
        is a required finite float. Dating this frame to the NaN epoch instead
        would assert a measurement that does not exist and draw a flat segment
        on the chart to prove it. The narrative names the epoch it broke at.
        """
        if self._non_finite is None:
            return None
        prev = self._prev_frame
        if prev is None:
            # Nothing finite was ever read, so there is no story to correct and
            # no honest number to put on a frame.
            return None

        key, epoch = self._non_finite
        narrative = narrate_diverged(
            epoch=epoch,
            metric=key,
            last_value=prev.primary_metric_value,
            last_epoch=prev.epoch,
            run_id=self.run_id,
            locale=self.locale,
        )
        frame = StoryFrame(
            run_id=self.run_id,
            seq=last_seq + 1,
            epoch=prev.epoch,
            # The run did not get further along by failing.
            progress=prev.progress,
            phase=prev.phase,
            grade=Grade.F,
            primary_metric_value=prev.primary_metric_value,
            primary_metric=prev.primary_metric,
            confidence=prev.confidence,
            narrative=narrative,
            # Its own cards, not none: the panel renders the last frame's
            # cards, so an empty list left a stale "Grade B+" card sitting
            # beside the F this frame reports.
            metaphor_cards=self._build_metaphor_cards(prev.phase, Grade.F),
            skill_dimensions=prev.skill_dimensions,
            milestones=[],
            warnings=[
                Warning(
                    kind="divergence",
                    epoch=epoch,
                    message="Something went wrong — the loss became undefined. "
                    "The teacher may need to lower the learning rate.",
                )
            ],
            task_type=self._effective_task(),
        )
        self._prev_frame = frame
        return frame

    def _ensure_milestones(self) -> None:
        if self._milestones is None:
            self._milestones = MilestoneTracker(
                run_id=self.run_id,
                task=self._effective_task(),
            )

    def _emit(self, event: MetricEvent) -> StoryFrame | None:
        """Build a StoryFrame for a primary-metric event, or None otherwise."""
        primary_key = self._effective_primary_key()
        if event.canonical_key != primary_key:
            return None  # only emit frames on primary metric updates

        assert self._milestones is not None  # callers run _ensure_milestones first
        primary_value = event.value

        # The primary metric can change once the task is detected (a run whose
        # first events were only losses starts on the CUSTOM fallback). Restart
        # the baseline/best bookkeeping so trajectory maths never mixes a loss
        # with an accuracy.
        if self._primary_key_used is not None and self._primary_key_used != primary_key:
            self._baseline = None
            self._best_primary = None
            self._best_epoch = None
            self._prev_primary = None
        self._primary_key_used = primary_key

        if self._baseline is None:
            self._baseline = primary_value

        progress = estimate_progress(
            current_epoch=event.epoch,
            total_epochs=self.total_epochs,
            step=event.step,
        )

        # Direction: for a known task, trust the task. For CUSTOM (e.g. a script
        # that logs only a loss curve and never accuracy), the task can't tell
        # us — infer from the metric NAME so a val_loss is correctly treated as
        # lower-is-better for phase/progress/grade.
        task = self._effective_task()
        # Direction belongs to the METRIC, not the task. R2 lives in the
        # regression task, whose other metrics are errors, so the task-level
        # answer said "lower is better" and an improving R2 run graded WORSE
        # than a worsening one. Trust the metric name whenever it is known and
        # fall back to the task only when it is not.
        name_dir = metric_lower_better(event.canonical_key or self.primary_metric)
        if name_dir is not None:
            lower_better = name_dir
        elif task is TaskType.CUSTOM:
            lower_better = False
        else:
            lower_better = is_lower_better(task, self.grade_config)

        # The phase is inferred from how far the metric has MOVED, which needs
        # at least two readings. With one, the baseline is the value itself, so
        # improvement is zero by construction and every run — however good the
        # model — was placed in AWAKENING and narrated as "random predictions"
        # or "first patterns emerge from the noise". A single sklearn fit reads
        # R² 0.996 and got exactly that, next to an A+.
        #
        # For a bounded higher-is-better metric there is another honest reading:
        # where the value sits on its own scale. Only for the first reading —
        # once there are two, real movement is the better signal.
        phase_baseline = self._baseline
        if (
            len(self._metric_history.get(primary_key, ())) < 2
            and not lower_better
            and 0.0 <= primary_value <= 1.0
        ):
            phase_baseline = 0.0

        phase = compute_phase(
            progress=progress,
            primary_value=primary_value,
            baseline=phase_baseline,
            lower_better=lower_better,
        )

        # Honest "advancement" 0–1: the clock when total length is known, else
        # the fraction of achievable metric improvement realised so far. Used
        # for both the progress bar and the maturity signal (NOT a statistical
        # prediction confidence).
        rel = relative_improvement(
            primary_value,
            self._baseline,
            lower_better=lower_better,
        )
        advancement = progress if progress is not None else (rel if rel is not None else 0.0)
        # A non-finite primary (diverged run) can make relative-improvement NaN;
        # clamp so the progress/confidence Field(ge=0, le=1) validators never
        # reject the frame. The raw metric value itself still serialises to null.
        if not math.isfinite(advancement):
            advancement = 0.0
        advancement = max(0.0, min(1.0, advancement))

        # CUSTOM metrics have no absolute quality scale (a "0.19 loss" is not a
        # fixed grade), so score them on improvement from baseline. Otherwise a
        # healthy, decreasing loss was graded against accuracy thresholds and
        # came out F — contradicting its own "trend is positive" narrative.
        # The absolute thresholds belong to a task's CANONICAL metric — the
        # first preferred key. A run whose primary metric is a secondary one
        # (PSNR inside "generative", whose bands are built for FID; WER inside
        # "nlp", built for perplexity) would be scored against a scale that has
        # nothing to do with it: PSNR graded A+ whether it improved or got
        # worse. And R2 inside "regression" was graded as if lower were better,
        # so an improving run scored WORSE than a worsening one. Where the
        # scale does not apply, grade on improvement from baseline instead.
        preferred = _PREFERRED_KEYS_FOR_TASK.get(task, ())
        on_scale = _ON_SCALE_KEYS.get(task) or (preferred[:1] and frozenset(preferred[:1]))
        off_scale = bool(preferred) and primary_key not in on_scale
        needs_trajectory = task is TaskType.CUSTOM or off_scale

        if not needs_trajectory or has_absolute_scale(primary_key):
            grade = compute_grade(
                task=task,
                primary_value=primary_value,
                config=self.grade_config,
                metric=primary_key,
            )
        elif self._baseline is not None and len(self._metric_history.get(primary_key, ())) >= 2:
            grade = grade_by_trajectory(self._baseline, primary_value, lower_better)
        else:
            # No scale to measure against and no movement to measure: one
            # reading of a metric whose units we do not know. Anything else
            # here is a guess dressed as a verdict — a single MAE used to be
            # graded against bands built for normalised targets, so an
            # excellent model came out F. "I" is what the enum has always had
            # for this, and both the dashboard and the extension already
            # colour it.
            grade = Grade.INCOMPLETE

        delta = primary_value - self._prev_primary if self._prev_primary is not None else 0.0

        # Honesty guard: the phase templates are driven by how far through
        # training we are, so a model stuck at chance level was still narrated
        # as "a diligent student" / "patterns are starting to click". Say what
        # is actually true when the metric has not meaningfully moved.
        # Track the run's own best so the story can't claim "peak form" while
        # sitting below a better earlier checkpoint.
        if self._best_primary is None or (
            primary_value < self._best_primary
            if lower_better
            else primary_value > self._best_primary
        ):
            self._best_primary = primary_value
            self._best_epoch = event.epoch

        past_peak = False
        if self._best_primary is not None and abs(self._best_primary) > 1e-9:
            drop = (
                (primary_value - self._best_primary)
                if lower_better
                else (self._best_primary - primary_value)
            ) / abs(self._best_primary)
            past_peak = drop > _PAST_PEAK_REL_DROP

        epochs_seen = len(self._metric_history.get(event.canonical_key, ()))
        # `rel` is the fraction of achievable improvement realised, so a run
        # that got WORSE scores at or below zero and clears this threshold as
        # easily as a genuinely flat one. Because this branch is tested before
        # `past_peak`, a metric that fell 0.79 -> 0.60 was narrated as "the
        # metric has barely moved ... the model is not learning yet" — on the
        # same screen as the overfitting warning it had just triggered. Not
        # merely a poor phrasing: a 24% decline is not "barely moved", and the
        # advice that follows (check the learning rate, then the data
        # pipeline) sends you after a setup bug that is not there.
        #
        # Stalled means flat. If the metric has actually slipped from its best,
        # `past_peak` is the honest description and it already says so.
        stalled = (
            epochs_seen >= _STALL_MIN_EPOCHS
            and rel is not None
            and rel < _STALL_REL_IMPROVEMENT
            and not past_peak
        )
        # A result, not a stage of training. Both conditions are needed: one
        # reading alone also describes epoch 1 of a live run, which genuinely
        # is the beginning of an arc. The absence of an epoch is what separates
        # them — a script that fits once and prints a score never numbers
        # anything, while every real training loop does.
        if event.epoch is None and epochs_seen <= 1:
            narrative = narrate_single_reading(
                primary_value=primary_value,
                run_id=self.run_id,
                locale=self.locale,
                metric=primary_key,
            )
        elif stalled and self._baseline is not None:
            narrative = narrate_stalled(
                epoch=event.epoch,
                primary_value=primary_value,
                baseline=self._baseline,
                epochs_seen=epochs_seen,
                run_id=self.run_id,
                locale=self.locale,
            )
        elif past_peak and self._best_primary is not None:
            narrative = narrate_past_peak(
                epoch=event.epoch,
                primary_value=primary_value,
                best_value=self._best_primary,
                best_epoch=self._best_epoch,
                run_id=self.run_id,
                locale=self.locale,
            )
        else:
            narrative = narrate(
                task=self._effective_task(),
                phase=phase,
                epoch=event.epoch,
                primary_value=primary_value,
                delta=delta,
                run_id=self.run_id,
                locale=self.locale,
                metric=primary_key,
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

        # A bounded metric outside [0, 1] is a units mistake or corrupt data,
        # never a very good model. Narrating "at 110.0%, the model approaches
        # its ceiling" interprets a number that cannot exist — the same fault
        # as the 123.6% this project shipped once. Say what is actually known.
        reason = impossible_reason(primary_key, primary_value)
        if reason is not None:
            shown = "NaN" if primary_value is None else f"{primary_value:.4g}"
            narrative = (
                f"{primary_key} reported {shown}, which {reason}. "
                f"No reading is given for this epoch."
            )

        frame = StoryFrame(
            run_id=self.run_id,
            seq=event.seq,
            epoch=event.epoch,
            progress=advancement,
            phase=phase,
            grade=grade,
            primary_metric_value=primary_value,
            primary_metric=primary_key,
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
            """Invert a lower-is-better metric into a [0,1] "skill" score.

            An unbounded metric needs SOME reference to land on a 0–1 axis, and
            these references are a judgement call, not a standard. The axis
            label therefore carries the divisor ("1 − MAE/30"), because a label
            reading "1 − MAE" lets a reader back out a value that is wrong by
            the scale factor.
            """
            return None if v is None else max(0.0, 1.0 - min(v / scale, 1.0))

        dims: dict[str, float] = {}
        task = self._effective_task()

        def _add(key: str, value: float | None) -> None:
            # Skip non-finite (a diverged NaN/Inf metric) — a radar axis needs a
            # real number, and it must not leak into the JSON payload.
            if value is not None and math.isfinite(value):
                dims[key] = value

        if task == TaskType.DETECTION:
            # YOLO / object-detection axes — every one is reported by the
            # Ultralytics parser, so the radar is full on real detection runs.
            _add("mAP50", _last("mAP50"))
            _add("mAP50-95", _last("mAP"))
            _add("Precision", _last("precision"))
            _add("Recall", _last("recall"))
            # Localisation quality: low box_loss → tight boxes.
            _add("1 − box_loss/4", _inv(_last("box_loss"), scale=4.0))
        elif task == TaskType.BIOMETRIC:
            _add("1 − EER/0.5", _inv(_last("EER"), scale=0.5))
            _add("TAR", _last("TAR"))
            _add("TAR@FAR=1e-3", _last("TAR_at_FAR_0_001"))
        elif task == TaskType.GAZE:
            _add("1 − MAE/30", _inv(_last("MAE"), scale=30.0))
            _add("1 − RMSE/30", _inv(_last("RMSE"), scale=30.0))
        elif task == TaskType.NLP:
            _add("1 − PPL/200", _inv(_last("perplexity"), scale=200.0))
            _add("BLEU", _last("bleu"))
            _add("ROUGE", _last("rouge"))
        elif task == TaskType.REGRESSION:
            _add("1 − MAE/2", _inv(_last("MAE"), scale=2.0))
            _add("1 − RMSE/2", _inv(_last("RMSE"), scale=2.0))

        # Classification axes — also act as the universal fallback so any run
        # that happens to log these gets them on the radar regardless of task.
        _add("Accuracy", _last("accuracy"))
        _add("Val Accuracy", _last("val_accuracy"))

        # "Fitting" and "Generalisation" derived from the loss history, made
        # SCALE-RELATIVE so they stay meaningful whatever the loss magnitude
        # (MSE in the tens, cross-entropy near 1, …). A fixed scale=1.0 pinned
        # both axes to 0 for any run whose loss exceeded 1.0 — i.e. most real
        # runs. Fitting = fraction of training loss reduced from the first
        # epoch; Generalisation = how closely val loss tracks train loss
        # (1.0 = no gap, lower = more overfitting).
        tl_hist = h.get("train_loss")
        vl_hist = h.get("val_loss")
        if tl_hist and tl_hist[0] > 0:
            _add("Fitting", max(0.0, min(1.0, 1.0 - tl_hist[-1] / tl_hist[0])))
        if tl_hist and vl_hist and vl_hist[-1] > 0:
            _add("Generalisation", max(0.0, min(1.0, tl_hist[-1] / vl_hist[-1])))

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
