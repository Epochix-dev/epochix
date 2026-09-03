from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from epochix.models import Warning

WarningKind = Literal["overfit", "plateau", "divergence", "lr_drop"]

_OVERFIT_WINDOW = 3  # val_loss must rise for N consecutive epochs
_PLATEAU_WINDOW = 5  # <1% improvement over N epochs
_PLATEAU_DELTA = 0.01
# Divergence measured against the best loss seen, not just the previous epoch.
# A run that doubles every epoch never trips a single-step 10x rule, yet 3.59 ->
# 2881 over eight epochs is the textbook picture of a diverging optimiser. The
# gradual case is also the common one: a loss usually explodes over several
# epochs before it finally prints `nan`, and `nan` itself never reaches this
# detector because the log parser will not read a non-numeric value.
_DIVERGE_GROWTH = 10.0


@dataclass
class WarningDetector:
    """Stateful detector for training pathologies."""

    _train_losses: deque[float] = field(default_factory=lambda: deque(maxlen=10), init=False)
    _val_losses: deque[float] = field(default_factory=lambda: deque(maxlen=10), init=False)
    _primary: deque[float] = field(default_factory=lambda: deque(maxlen=10), init=False)
    _lr_prev: float | None = field(default=None, init=False)
    _best_train_loss: float | None = field(default=None, init=False)
    _fired: set[str] = field(default_factory=set, init=False)

    def update(
        self,
        epoch: float | None,
        train_loss: float | None = None,
        val_loss: float | None = None,
        primary_value: float | None = None,
        lr: float | None = None,
    ) -> list[Warning]:
        warnings: list[Warning] = []

        if train_loss is not None:
            self._train_losses.append(train_loss)
        if val_loss is not None:
            self._val_losses.append(val_loss)
        if primary_value is not None:
            self._primary.append(primary_value)

        # Divergence: loss is NaN or spiked 10×
        if train_loss is not None:
            if math.isnan(train_loss) or math.isinf(train_loss):
                warnings.append(
                    Warning(
                        kind="divergence",
                        epoch=epoch,
                        message="Something went wrong — the loss became undefined. "
                        "The teacher may need to lower the learning rate.",
                    )
                )
            elif len(self._train_losses) >= 2 and train_loss > self._train_losses[-2] * 10:
                warnings.append(
                    Warning(
                        kind="divergence",
                        epoch=epoch,
                        message="The loss has spiked unexpectedly. "
                        "The model may have stepped too far in one direction.",
                    )
                )
            elif (
                self._best_train_loss is not None
                and self._best_train_loss > 0
                and train_loss > self._best_train_loss * _DIVERGE_GROWTH
                and "divergence" not in self._fired
            ):
                self._fired.add("divergence")
                warnings.append(
                    Warning(
                        kind="divergence",
                        epoch=epoch,
                        message="The loss is climbing away from where it started. "
                        "The teacher may need to lower the learning rate.",
                    )
                )

            if math.isfinite(train_loss) and (
                self._best_train_loss is None or train_loss < self._best_train_loss
            ):
                self._best_train_loss = train_loss

        # Overfitting: val_loss rising while train_loss falling for N epochs
        if (
            len(self._val_losses) >= _OVERFIT_WINDOW
            and len(self._train_losses) >= _OVERFIT_WINDOW
            and "overfit" not in self._fired
        ):
            val_rising = all(
                self._val_losses[i] < self._val_losses[i + 1] for i in range(-_OVERFIT_WINDOW, -1)
            )
            train_falling = all(
                self._train_losses[i] > self._train_losses[i + 1]
                for i in range(-_OVERFIT_WINDOW, -1)
            )
            if val_rising and train_falling:
                self._fired.add("overfit")
                warnings.append(
                    Warning(
                        kind="overfit",
                        epoch=epoch,
                        message="The model may be memorising the study material "
                        "instead of understanding it.",
                    )
                )

        # Plateau: <1% improvement in primary metric over N epochs
        if len(self._primary) >= _PLATEAU_WINDOW and "plateau" not in self._fired:
            window = list(self._primary)[-_PLATEAU_WINDOW:]
            span = max(window) - min(window)
            ref = abs(window[0]) + 1e-9
            if span / ref < _PLATEAU_DELTA:
                self._fired.add("plateau")
                warnings.append(
                    Warning(
                        kind="plateau",
                        epoch=epoch,
                        message="Learning has slowed. The model has stopped finding new patterns.",
                    )
                )

        # LR drop
        if lr is not None:
            if self._lr_prev is not None and lr < self._lr_prev * 0.6:
                warnings.append(
                    Warning(
                        kind="lr_drop",
                        epoch=epoch,
                        message=f"Learning rate decreased from {self._lr_prev:.2e} to {lr:.2e}.",
                    )
                )
            self._lr_prev = lr

        return warnings
