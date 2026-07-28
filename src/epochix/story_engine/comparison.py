"""Explain *why* one run beat another.

Every tool can overlay two curves. None of them says what the overlay means.
This assembles a plain-English account of the difference from facts the engine
already computes per run — the best value and the epoch it happened, whether a
run continued past its peak, whether it was still improving when it stopped.

Honesty rules, in order of precedence:

1. Runs measured on different primary metrics are **not comparable**, and this
   says so rather than comparing them anyway.
2. A gap smaller than the runs' own epoch-to-epoch movement is **not a result**.
   It is reported as no meaningful difference, never as a winner.
3. Nothing here implies causation. It reports what the curves did; it does not
   claim a hyperparameter caused it.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from epochix.story_engine.grade import metric_lower_better
from epochix.story_engine.narrator import _load_special

# A gap must exceed this multiple of the runs' own median epoch-to-epoch
# movement before it is called a difference. Two runs of the same config
# routinely land a fraction of a point apart; that is noise, not a finding.
_NOISE_MULTIPLE = 1.0

# Below this relative change over the closing epochs, a run is treated as
# having settled rather than still climbing.
_STILL_IMPROVING_REL = 0.002


@dataclass(frozen=True)
class RunTrajectory:
    """The facts about one run that a comparison may honestly use."""

    name: str
    primary_metric: str
    values: list[tuple[float, float]]  # (epoch, value), in epoch order
    grade: str | None = None

    @property
    def lower_better(self) -> bool:
        return metric_lower_better(self.primary_metric) is True

    @property
    def final_value(self) -> float:
        return self.values[-1][1]

    @property
    def final_epoch(self) -> float:
        return self.values[-1][0]

    @property
    def best(self) -> tuple[float, float]:
        """``(epoch, value)`` of this run's best point."""
        key = min if self.lower_better else max
        return key(self.values, key=lambda ev: ev[1])

    @property
    def noise(self) -> float:
        """Median absolute change between consecutive epochs."""
        deltas = [
            abs(self.values[i][1] - self.values[i - 1][1]) for i in range(1, len(self.values))
        ]
        return statistics.median(deltas) if deltas else 0.0

    def is_past_peak(self) -> bool:
        """True when the run ended meaningfully worse than its own best."""
        best_epoch, best_value = self.best
        if best_epoch >= self.final_epoch:
            return False
        drop = self.final_value - best_value if self.lower_better else best_value - self.final_value
        return drop > self.noise

    def was_still_improving(self) -> bool:
        """True when the closing epochs were still moving in the good direction."""
        if len(self.values) < 4:
            return False
        window = self.values[-3:]
        change = window[0][1] - window[-1][1] if self.lower_better else window[-1][1] - window[0][1]
        scale = abs(window[0][1]) or 1.0
        return change / scale > _STILL_IMPROVING_REL


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def _epoch(value: float) -> str:
    return str(int(value))


def _fill(template: str, **kwargs: str) -> str:
    for key, replacement in kwargs.items():
        template = template.replace("{" + key + "}", replacement)
    return template


def narrate_comparison(runs: list[RunTrajectory], locale: str = "en") -> str:
    """Explain the difference between runs, or why they cannot be compared."""
    usable = [r for r in runs if len(r.values) >= 2]
    if len(usable) < 2:
        return _load_special(
            "_compare_insufficient", locale, "Not enough of the runs have data to compare."
        )[0]

    metrics = {r.primary_metric for r in usable}
    if len(metrics) > 1:
        return _fill(
            _load_special(
                "_compare_incomparable",
                locale,
                "These runs measure different things ({metrics}), so their numbers "
                "are not comparable.",
            )[0],
            metrics=", ".join(sorted(metrics)),
        )

    lower_better = usable[0].lower_better
    ranked = sorted(usable, key=lambda r: r.final_value, reverse=not lower_better)
    winner, loser = ranked[0], ranked[-1]

    gap = abs(winner.final_value - loser.final_value)
    noise = max(winner.noise, loser.noise)

    if gap <= noise * _NOISE_MULTIPLE:
        return _fill(
            _load_special(
                "_compare_noise",
                locale,
                "{a} and {b} finished within {gap} of each other ({metric}), which is "
                "no larger than the epoch-to-epoch movement in either run. On this "
                "evidence there is no meaningful difference between them.",
            )[0],
            a=usable[0].name,
            b=usable[1].name,
            gap=_fmt(gap),
            metric=winner.primary_metric,
        )

    parts = [
        _fill(
            _load_special(
                "_compare_win",
                locale,
                "{winner} finished ahead of {loser}: {win_value} against {lose_value} ({metric}).",
            )[0],
            winner=winner.name,
            loser=loser.name,
            win_value=_fmt(winner.final_value),
            lose_value=_fmt(loser.final_value),
            metric=winner.primary_metric,
        )
    ]

    if loser.is_past_peak():
        best_epoch, best_value = loser.best
        recovered = abs(best_value - winner.final_value)
        parts.append(
            _fill(
                _load_special(
                    "_compare_pastpeak",
                    locale,
                    "{loser} peaked at {best} on epoch {best_epoch} and ended worse, at "
                    "{lose_value}. Had it stopped at its best the gap would have been "
                    "{recovered} rather than {gap}.",
                )[0],
                loser=loser.name,
                best=_fmt(best_value),
                best_epoch=_epoch(best_epoch),
                lose_value=_fmt(loser.final_value),
                recovered=_fmt(recovered),
                gap=_fmt(gap),
            )
        )

    if winner.was_still_improving():
        parts.append(
            _fill(
                _load_special(
                    "_compare_stillimproving",
                    locale,
                    "{winner} was still improving when it stopped, so its result is "
                    "probably not its ceiling.",
                )[0],
                winner=winner.name,
            )
        )

    return " ".join(parts)


def trajectory_from_frames(
    name: str,
    frames: list[object],
    grade: str | None = None,
) -> RunTrajectory | None:
    """Build a trajectory from stored :class:`StoryFrame` records.

    Frames whose ``primary_metric`` differs from the run's dominant one are
    dropped: an early frame can predate task detection and measure something
    else, and mixing them would compare two different quantities.
    """
    counts: dict[str, int] = {}
    for frame in frames:
        key = getattr(frame, "primary_metric", None)
        if key:
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return None
    dominant = max(counts, key=lambda k: counts[k])

    values: list[tuple[float, float]] = []
    for frame in frames:
        if getattr(frame, "primary_metric", None) != dominant:
            continue
        epoch = getattr(frame, "epoch", None)
        value = getattr(frame, "primary_metric_value", None)
        if epoch is None or value is None:
            continue
        values.append((float(epoch), float(value)))

    if len(values) < 2:
        return None
    values.sort(key=lambda ev: ev[0])
    return RunTrajectory(name=name, primary_metric=dominant, values=values, grade=grade)
