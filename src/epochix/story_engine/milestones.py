from __future__ import annotations

from dataclasses import dataclass, field

from epochix.enums import TaskType
from epochix.models import Milestone
from epochix.story_engine.grade import is_unit_bounded
from epochix.story_engine.messages import message

_LOWER_BETTER_TASKS = frozenset(
    {TaskType.NLP, TaskType.BIOMETRIC, TaskType.GAZE, TaskType.REGRESSION}
)

# Thresholds for "first_above_N" milestones.
_ACCURACY_THRESHOLDS = [0.25, 0.50, 0.75, 0.90]

# Bounded to [0, 1] but not a fraction of anything: "crossed 50%" of an R²
# or an SSIM is not a sentence with a meaning.
_NOT_A_FRACTION = frozenset({"R2", "SSIM"})


@dataclass
class MilestoneTracker:
    run_id: str
    task: TaskType
    locale: str = "en"

    _best: float = field(default=float("-inf"), init=False)
    _crossed_thresholds: set[float] = field(default_factory=set, init=False)
    _fired: set[str] = field(default_factory=set, init=False)
    # (gain, seq, epoch) of each reading against the one before it.
    _deltas: list[tuple[float, int, float | None]] = field(default_factory=list, init=False)
    _metric: str | None = field(default=None, init=False)

    def _lower_better(self, lower_better: bool | None) -> bool:
        # The engine knows the metric's direction; the task is only a
        # fallback. Taking it from the task treated a custom run graded on
        # val_loss, and an FID, as higher-is-better: the WORST loss was
        # "best", and the first loss of 1.2 "crossed 25%, 50%, 75% and 90%".
        if lower_better is not None:
            return lower_better
        return self.task in _LOWER_BETTER_TASKS

    @staticmethod
    def _is_fraction(metric: str | None) -> bool:
        return is_unit_bounded(metric) and metric not in _NOT_A_FRACTION

    def check(
        self,
        epoch: float | None,
        seq: int,
        primary_value: float,
        prev_value: float | None = None,
        *,
        metric: str | None = None,
        lower_better: bool | None = None,
    ) -> list[Milestone]:
        fired: list[Milestone] = []
        lower = self._lower_better(lower_better)

        # Best, deltas and thresholds belong to one metric. If the engine
        # settles on a different primary metric, comparing across the two
        # would compare a loss with an accuracy.
        switched = metric != self._metric
        if switched:
            self._metric = metric
            self._best = float("-inf")
            self._crossed_thresholds.clear()
            self._deltas.clear()

        if lower:
            is_best = primary_value < self._best if self._best != float("-inf") else True
        else:
            is_best = primary_value > self._best

        if is_best:
            if "best_so_far" not in self._fired:
                fired.append(
                    Milestone(
                        run_id=self.run_id,
                        seq=seq,
                        kind="best_so_far",
                        epoch=epoch,
                        value=primary_value,
                        message=message("ms_best", self.locale, value=f"{primary_value:.4f}"),
                    )
                )
                self._fired.add("best_so_far")
            self._best = primary_value

        # "Crossed N%" only means something for a metric that IS a fraction
        # of its maximum and is read the right way up. Anything else — a loss,
        # FID, perplexity, an accuracy logged as 0-100 — would have it
        # announcing thresholds the model never reached.
        if (
            metric is not None
            and not lower
            and self._is_fraction(metric)
            and 0.0 <= primary_value <= 1.0
        ):
            for threshold in _ACCURACY_THRESHOLDS:
                kind = f"first_above_{int(threshold * 100)}"
                if (
                    primary_value >= threshold
                    and threshold not in self._crossed_thresholds
                    and kind not in self._fired
                ):
                    self._crossed_thresholds.add(threshold)
                    self._fired.add(kind)
                    fired.append(
                        Milestone(
                            run_id=self.run_id,
                            seq=seq,
                            kind=kind,
                            epoch=epoch,
                            value=primary_value,
                            message=message(
                                "ms_crossed",
                                self.locale,
                                pct=str(int(threshold * 100)),
                                value=f"{primary_value:.4f}",
                            ),
                        )
                    )

        # Track IMPROVEMENTS for biggest_jump (computed at run end). This took
        # the absolute change, so the largest step the wrong way — a loss
        # jumping up — was reported as the "biggest single-epoch improvement".
        if prev_value is not None and not switched:
            gain = prev_value - primary_value if lower else primary_value - prev_value
            self._deltas.append((gain, seq, epoch))

        return fired

    def finalize(self, seq: int, epoch: float | None) -> list[Milestone]:
        """Call at end-of-run to emit biggest_jump + training_complete.

        The biggest jump is only known at the end, but it happened at one
        reading, and carries that reading's seq and epoch. It was stamped with
        the run's last ones, so a timeline put "biggest single-epoch
        improvement" at the final epoch. The first of equal gains wins.
        """
        result: list[Milestone] = []

        best = max(self._deltas, key=lambda d: d[0], default=None)
        if best is not None and best[0] > 0 and "biggest_jump" not in self._fired:
            max_delta, jump_seq, jump_epoch = best
            self._fired.add("biggest_jump")
            result.append(
                Milestone(
                    run_id=self.run_id,
                    seq=jump_seq,
                    kind="biggest_jump",
                    epoch=jump_epoch,
                    value=max_delta,
                    message=message("ms_biggest_jump", self.locale, value=f"{max_delta:.4f}"),
                )
            )

        result.append(
            Milestone(
                run_id=self.run_id,
                seq=seq + 1,
                kind="training_complete",
                epoch=epoch,
                value=self._best if self._best != float("-inf") else None,
                message=message("ms_complete", self.locale),
            )
        )
        return result
