from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from epochix.models import Warning
from epochix.story_engine.messages import message

WarningKind = Literal[
    "overfit", "overfit_cleared", "plateau", "plateau_cleared", "divergence", "lr_drop"
]

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

_CLEARED = "_cleared"


def standing_warnings(warnings: Iterable[Warning]) -> list[Warning]:
    """The warnings still in force once every withdrawal has been applied.

    A `<kind>_cleared` warning is not one to show: it withdraws the `<kind>`
    warnings before it. The dashboard's store does the same as frames arrive.
    """
    standing: list[Warning] = []
    for warning in warnings:
        if warning.kind.endswith(_CLEARED):
            withdrawn = warning.kind[: -len(_CLEARED)]
            standing = [w for w in standing if w.kind != withdrawn]
        elif all(w.message != warning.message for w in standing):
            standing.append(warning)
    return standing


@dataclass
class WarningDetector:
    """Stateful detector for training pathologies."""

    locale: str = "en"
    _train_losses: deque[float] = field(default_factory=lambda: deque(maxlen=10), init=False)
    _val_losses: deque[float] = field(default_factory=lambda: deque(maxlen=10), init=False)
    _primary: deque[float] = field(default_factory=lambda: deque(maxlen=10), init=False)
    _lr_prev: float | None = field(default=None, init=False)
    _best_train_loss: float | None = field(default=None, init=False)
    _best_val_loss: float | None = field(default=None, init=False)
    # The best validation loss when the overfit warning fired. Beating it later
    # disproves the warning; see the overfit block below.
    _overfit_mark: float | None = field(default=None, init=False)
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
                        message=message("warn_nan", self.locale),
                    )
                )
            elif len(self._train_losses) >= 2 and train_loss > self._train_losses[-2] * 10:
                warnings.append(
                    Warning(
                        kind="divergence",
                        epoch=epoch,
                        message=message("warn_spike", self.locale),
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
                        message=message("warn_climb", self.locale),
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
                self._overfit_mark = self._best_val_loss
                warnings.append(
                    Warning(
                        kind="overfit",
                        epoch=epoch,
                        message=message("warn_overfit", self.locale),
                    )
                )

        # A validation loss that later beats its best from before the rise was
        # a blip, not memorising. A ResNet-18 on CIFAR-10 rose 0.862 -> 0.867 ->
        # 1.229 during its learning-rate warm-up, fell to a new best the next
        # epoch and kept falling to its lowest at the last one — while the
        # dashboard still told the reader to "stop at the best validation
        # epoch". Withdraw the warning, and let it fire again if it recurs.
        if (
            val_loss is not None
            and self._overfit_mark is not None
            and "overfit" in self._fired
            and val_loss < self._overfit_mark
        ):
            self._fired.discard("overfit")
            self._overfit_mark = None
            warnings.append(
                Warning(
                    kind="overfit_cleared",
                    epoch=epoch,
                    message=message("warn_overfit_cleared", self.locale),
                )
            )
        if (
            val_loss is not None
            and math.isfinite(val_loss)
            and (self._best_val_loss is None or val_loss < self._best_val_loss)
        ):
            self._best_val_loss = val_loss

        # Plateau: the primary metric moved less than 1% over the last N
        # readings. The warning describes those N readings, so it stands only
        # while it is true of them: a real Keras run flattened for five epochs
        # in the middle, then climbed again to its best at the last one, and
        # the banner still said it had stopped while the grade card beside it
        # said "still improving". Withdraw it when the window is no longer
        # flat, and let it fire again if the run flattens later.
        if primary_value is not None and len(self._primary) >= _PLATEAU_WINDOW:
            window = list(self._primary)[-_PLATEAU_WINDOW:]
            span = max(window) - min(window)
            ref = abs(window[0]) + 1e-9
            flat = span / ref < _PLATEAU_DELTA
            if flat and "plateau" not in self._fired:
                self._fired.add("plateau")
                warnings.append(
                    Warning(
                        kind="plateau",
                        epoch=epoch,
                        message=message("warn_plateau", self.locale),
                    )
                )
            elif not flat and "plateau" in self._fired:
                self._fired.discard("plateau")
                warnings.append(
                    Warning(
                        kind="plateau_cleared",
                        epoch=epoch,
                        message=message("warn_plateau_cleared", self.locale),
                    )
                )

        # LR drop
        if lr is not None:
            if self._lr_prev is not None and lr < self._lr_prev * 0.6:
                warnings.append(
                    Warning(
                        kind="lr_drop",
                        epoch=epoch,
                        message=message(
                            "warn_lr_drop",
                            self.locale,
                            old=f"{self._lr_prev:.2e}",
                            new=f"{lr:.2e}",
                        ),
                    )
                )
            self._lr_prev = lr

        return warnings
