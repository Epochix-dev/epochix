from __future__ import annotations

from model_story.enums import Phase


def compute_phase(
    progress: float,
    primary_value: float,
    baseline: float,
    target: float,
) -> Phase:
    """Hybrid phase detector using both progress and relative metric improvement.

    Args:
        progress:      0.0–1.0 fraction of total epochs completed.
        primary_value: Current primary metric value (accuracy, mAP, etc.).
        baseline:      Value at epoch 0 (or first recorded epoch).
        target:        Theoretical maximum (1.0 for accuracy/mAP, or pre-configured).
    """
    if progress < 0.10:
        return Phase.AWAKENING

    span = target - baseline
    relative = (primary_value - baseline) / (span + 1e-9) if span > 0 else progress

    if progress < 0.40 or relative < 0.40:
        return Phase.LEARNING
    if progress < 0.70 or relative < 0.75:
        return Phase.UNDERSTANDING
    if progress < 0.95 or relative < 0.95:
        return Phase.MASTERING
    return Phase.POLISHING


def estimate_progress(
    current_epoch: float | None,
    total_epochs: int | None,
    step: int | None = None,
    total_steps: int | None = None,
) -> float:
    """Best-effort 0–1 progress estimate from whatever info is available."""
    if current_epoch is not None and total_epochs and total_epochs > 0:
        return min(current_epoch / total_epochs, 1.0)
    if step is not None and total_steps and total_steps > 0:
        return min(step / total_steps, 1.0)
    # Fall back to a small non-zero value so AWAKENING fires immediately
    return 0.05
