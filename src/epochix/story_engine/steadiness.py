"""Whether a metric's readings can be compared one with another.

Every conclusion the engine draws sets one reading against another: this one
against the one before (a spike), against the best so far (past its peak), or
against the first (the grade of a metric with no scale). That is sound when
the next reading of an unchanged model would come out about the same, as a
validation loss does. It is not when each reading is one batch's loss. A LoRA
trainer prints nothing else, and on a diffusion model that number depends
mostly on which noise level the batch drew: a recorded run
(tests/fixtures/logs/diffusers_lora_real.log) moved by a factor of 2.6
between neighbours on the median and by 17 at most, with nothing wrong. Its
story was "past its best … use early stopping" from the second step, a letter
that went from F to A+ and back, and a divergence warning raised four times.

Two measurements of the series itself tell such a metric apart, and neither
is enough alone:

* how often it changes direction. A series with no order to it turns at two
  readings in three. But so does nanoGPT's loss per iteration (62%), which
  falls from 4.2 to 1.7 in plain sight: its wobble is small beside its trend.
* how far it moves between neighbours, as a share of the larger of the two.
  Large on its own is a fast start: a loss halving every epoch moves 50% a
  reading and never turns.

A metric is unsteady when it does both. Measured over every prefix of every
series in demo/ and tests/fixtures/logs/: with these thresholds the only
story metric or training loss ever called unsteady is the LoRA run's, from
its sixth reading on (median step 66%; an older 1,500-step SDXL run, not in
the repository, 75%). Among story metrics and training losses that turn half
the time, the next largest step is 16%, the ImageNet example's loss per
batch. (A gradient norm and a format sample's `dfl_loss` are unsteady by this
measure too; nothing is concluded from either.)

Nothing here smooths a reading or stands in for one. An unsteady metric is
charted as logged; what changes is what is concluded from it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

# Fewer readings than this say nothing either way. With four or five, the
# fifth reading of a format sample's validation accuracy
# (pytorch_lightning_long.log) is called unsteady; with six, nothing is.
UNSTEADY_MIN_READINGS = 6
# The readings looked at: the most recent ones, so a run is judged on how it
# reads now, and the work per frame does not grow with the run.
UNSTEADY_WINDOW = 50
# It changes direction at this share of the readings that could be a turn…
UNSTEADY_TURN_SHARE = 0.5
# …and its median step between neighbours is this share of the larger one.
UNSTEADY_STEP = 0.25


@dataclass(frozen=True)
class Swing:
    """How a metric's recent readings moved."""

    readings: int  # how many were looked at
    turns: int  # readings at which the series changed direction
    step: float  # median |change| between neighbours, as a share of the larger

    @property
    def step_text(self) -> str:
        """The step as a sentence quotes it: a whole percentage."""
        return f"{int(self.step * 100 + 0.5)}%"


def swing(values: Sequence[float]) -> Swing | None:
    """How the last readings of *values* moved, or None with fewer than three."""
    recent = values[-UNSTEADY_WINDOW:]
    if len(recent) < 3:
        return None
    turns = 0
    steps: list[float] = []
    for i in range(1, len(recent)):
        before, here = recent[i - 1], recent[i]
        larger = max(abs(before), abs(here))
        steps.append(abs(here - before) / larger if larger > 0 else 0.0)
        if i + 1 < len(recent):
            after = recent[i + 1]
            if (here > before and after < here) or (here < before and after > here):
                turns += 1
    return Swing(readings=len(recent), turns=turns, step=median(steps))


def unsteady(values: Sequence[float]) -> Swing | None:
    """The swing of *values* when one reading says little about the run, else None."""
    if len(values) < UNSTEADY_MIN_READINGS:
        return None
    found = swing(values)
    if (
        found is not None
        and found.turns >= UNSTEADY_TURN_SHARE * (found.readings - 2)
        and found.step >= UNSTEADY_STEP
    ):
        return found
    return None
