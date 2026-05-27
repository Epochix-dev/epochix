from __future__ import annotations

from dataclasses import dataclass, field

from epochix.enums import TaskType
from epochix.models import Milestone

_LOWER_BETTER_TASKS = frozenset(
    {TaskType.NLP, TaskType.BIOMETRIC, TaskType.GAZE, TaskType.REGRESSION}
)

# Thresholds for "first_above_N" milestones (higher-is-better tasks only)
_ACCURACY_THRESHOLDS = [0.25, 0.50, 0.75, 0.90]


@dataclass
class MilestoneTracker:
    run_id: str
    task: TaskType

    _best: float = field(default=float("-inf"), init=False)
    _crossed_thresholds: set[float] = field(default_factory=set, init=False)
    _fired: set[str] = field(default_factory=set, init=False)
    _deltas: list[float] = field(default_factory=list, init=False)

    def _lower_better(self) -> bool:
        return self.task in _LOWER_BETTER_TASKS

    def check(
        self,
        epoch: float | None,
        seq: int,
        primary_value: float,
        prev_value: float | None = None,
    ) -> list[Milestone]:
        fired: list[Milestone] = []

        if self._lower_better():
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
                        message=f"New best: {primary_value:.4f}",
                    )
                )
                self._fired.add("best_so_far")
            self._best = primary_value

        # first_above thresholds (higher-is-better tasks only)
        if not self._lower_better():
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
                            message=f"Crossed {int(threshold * 100)}%: {primary_value:.4f}",
                        )
                    )

        # Track deltas for biggest_jump (computed at run end)
        if prev_value is not None:
            self._deltas.append(abs(primary_value - prev_value))

        return fired

    def finalize(self, seq: int, epoch: float | None) -> list[Milestone]:
        """Call at end-of-run to emit biggest_jump + training_complete."""
        result: list[Milestone] = []

        if self._deltas and "biggest_jump" not in self._fired:
            max_delta = max(self._deltas)
            self._fired.add("biggest_jump")
            result.append(
                Milestone(
                    run_id=self.run_id,
                    seq=seq,
                    kind="biggest_jump",
                    epoch=epoch,
                    value=max_delta,
                    message=f"Biggest single-epoch improvement: {max_delta:.4f}",
                )
            )

        result.append(
            Milestone(
                run_id=self.run_id,
                seq=seq + 1,
                kind="training_complete",
                epoch=epoch,
                value=self._best if self._best != float("-inf") else None,
                message="Training completed.",
            )
        )
        return result
