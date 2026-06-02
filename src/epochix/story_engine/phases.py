from __future__ import annotations

from epochix.enums import Phase


def relative_improvement(
    primary_value: float,
    baseline: float,
    *,
    lower_better: bool = False,
    ideal: float | None = None,
) -> float | None:
    """Fraction of the achievable improvement realised so far, in [0, 1].

    Direction-aware: for higher-is-better metrics the ideal defaults to 1.0
    (accuracy/mAP/F1 are normalised to [0, 1]); for lower-is-better metrics
    (loss, MAE, EER, perplexity) the ideal defaults to 0.0 and improvement
    means moving *down* from the baseline. Returns ``None`` when the span is
    degenerate (baseline already at the ideal), so callers can fall back.
    """
    if ideal is None:
        ideal = 0.0 if lower_better else 1.0
    span = (baseline - ideal) if lower_better else (ideal - baseline)
    if abs(span) <= 1e-9:
        return None
    improved = (baseline - primary_value) if lower_better else (primary_value - baseline)
    return max(0.0, min(1.0, improved / span))


def compute_phase(
    progress: float | None,
    primary_value: float,
    baseline: float,
    *,
    lower_better: bool = False,
    ideal: float | None = None,
) -> Phase:
    """Hybrid phase detector using both progress and relative metric improvement.

    Args:
        progress:      0.0–1.0 fraction of training completed, or ``None`` when
                       the total length is unknown (then advancement is driven
                       purely by relative metric improvement).
        primary_value: Current primary metric value (accuracy, mAP, loss, …).
        baseline:      Value at the first recorded epoch.
        lower_better:  True for loss-like metrics where smaller is better.
        ideal:         Optional override for the metric's ideal value.
    """
    rel = relative_improvement(
        primary_value,
        baseline,
        lower_better=lower_better,
        ideal=ideal,
    )
    # When the metric span is degenerate, lean on the clock (or 0 if unknown).
    relative = rel if rel is not None else (progress if progress is not None else 0.0)
    # Advancement = the clock when we have one, else metric-driven progress.
    adv = progress if progress is not None else relative

    if adv < 0.10:
        return Phase.AWAKENING
    if adv < 0.40 or relative < 0.40:
        return Phase.LEARNING
    if adv < 0.70 or relative < 0.75:
        return Phase.UNDERSTANDING
    if adv < 0.95 or relative < 0.95:
        return Phase.MASTERING
    return Phase.POLISHING


def estimate_progress(
    current_epoch: float | None,
    total_epochs: int | None,
    step: int | None = None,
    total_steps: int | None = None,
) -> float | None:
    """Best-effort 0–1 progress fraction, or ``None`` when it can't be known.

    Returning ``None`` (rather than a fabricated constant) lets the phase
    detector advance on real metric improvement instead of pretending the run
    is stuck at the start when no total length was reported.
    """
    if current_epoch is not None and total_epochs and total_epochs > 0:
        return min(current_epoch / total_epochs, 1.0)
    if step is not None and total_steps and total_steps > 0:
        return min(step / total_steps, 1.0)
    return None
