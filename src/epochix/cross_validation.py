"""Cross-validation results as the log reported them.

Fold scores are not a series — their order carries no meaning — so the
universal parser collects them instead of charting them, and charts one value:
the mean, or for a parameter search (GridSearchCV and friends) the mean of the
setting the search chose. Everything else it read used to be discarded once
the run was parsed. ``epochix check`` printed every candidate, but no export
could, so the one thing a search exists to show — how the settings compared —
never left the terminal.

The raw fold readings are now kept on the run (``run.config["cross_validation"]``)
and ranked here, once, for ``epochix check`` and every export alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, stdev
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class FoldResult:
    """One metric of one setting, across its folds."""

    metric: str
    # The parameter setting as the log printed it; "" for a plain cross-validation.
    setting: str
    mean: float
    # None with a single fold: one number has no spread.
    std: float | None
    lowest: float
    highest: float
    folds: int
    # The setting a search picked, and so the value the run was charted and
    # graded on. Never set for a plain cross-validation or a one-setting search.
    chosen: bool


def record(
    folds: Mapping[str, list[float]],
    candidates: Mapping[str, Mapping[str, list[float]]],
) -> dict[str, Any] | None:
    """What a run keeps: the fold readings exactly as read, or None.

    Two readings of a metric before it counts as a fold set, as in the
    parser's flush — one stray number is not a cross-validation.
    """
    kept = {key: list(values) for key, values in folds.items() if len(values) >= 2}
    if not kept:
        return None
    return {
        "folds": kept,
        "candidates": {
            setting: {key: list(values) for key, values in metrics.items()}
            for setting, metrics in candidates.items()
        },
    }


def summarise(cv: Mapping[str, Any]) -> list[FoldResult]:
    """Every setting's result per metric, best first within each metric.

    scikit-learn scorers are higher-is-better by construction (losses arrive
    negated, as ``neg_mean_squared_error``), so best is the highest mean — the
    same choice the parser makes when it charts the winner. Ties keep the
    order the log printed them in, again as the parser does.
    """
    folds: Mapping[str, list[float]] = cv.get("folds") or {}
    candidates: Mapping[str, Mapping[str, list[float]]] = cv.get("candidates") or {}
    rows: list[FoldResult] = []
    for metric in sorted(folds):
        if candidates:
            ranked = sorted(
                ((setting, m[metric]) for setting, m in candidates.items() if m.get(metric)),
                key=lambda pair: fmean(pair[1]),
                reverse=True,
            )
            search = len(candidates) > 1
            rows.extend(
                _result(metric, setting, values, chosen=search and rank == 0)
                for rank, (setting, values) in enumerate(ranked)
            )
        elif len(folds[metric]) >= 2:
            rows.append(_result(metric, "", folds[metric], chosen=False))
    return rows


def is_search(cv: Mapping[str, Any]) -> bool:
    """Whether these folds came from a search over more than one setting."""
    return len(cv.get("candidates") or {}) > 1


def _result(metric: str, setting: str, values: list[float], *, chosen: bool) -> FoldResult:
    return FoldResult(
        metric=metric,
        setting=setting,
        mean=fmean(values),
        std=stdev(values) if len(values) > 1 else None,
        lowest=min(values),
        highest=max(values),
        folds=len(values),
        chosen=chosen,
    )
