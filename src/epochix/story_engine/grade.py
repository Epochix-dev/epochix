from __future__ import annotations

from epochix.enums import Grade, TaskType
from epochix.story_engine.config_loader import GradeConfig

# Default thresholds per task type.
# For accuracy/mAP/F1: higher = better (threshold = minimum value for that grade).
# For EER/loss/perplexity: lower = better (threshold = maximum value for that grade).
# Format: list of (Grade, threshold) sorted from best to worst.
_DEFAULT_THRESHOLDS: dict[TaskType, list[tuple[Grade, float]]] = {
    TaskType.CLASSIFICATION: [
        (Grade.A_PLUS, 0.95),
        (Grade.A, 0.90),
        (Grade.A_MINUS, 0.87),
        (Grade.B_PLUS, 0.82),
        (Grade.B, 0.75),
        (Grade.B_MINUS, 0.70),
        (Grade.C_PLUS, 0.65),
        (Grade.C, 0.60),
        (Grade.C_MINUS, 0.55),
        (Grade.D, 0.50),
        (Grade.F, 0.0),
    ],
    TaskType.DETECTION: [
        (Grade.A_PLUS, 0.75),
        (Grade.A, 0.65),
        (Grade.A_MINUS, 0.58),
        (Grade.B_PLUS, 0.50),
        (Grade.B, 0.42),
        (Grade.B_MINUS, 0.35),
        (Grade.C_PLUS, 0.28),
        (Grade.C, 0.20),
        (Grade.C_MINUS, 0.15),
        (Grade.D, 0.08),
        (Grade.F, 0.0),
    ],
    TaskType.NLP: [
        # Perplexity: lower = better. Thresholds are MAXIMUM values for each grade.
        (Grade.A_PLUS, 10.0),
        (Grade.A, 20.0),
        (Grade.A_MINUS, 30.0),
        (Grade.B_PLUS, 50.0),
        (Grade.B, 80.0),
        (Grade.B_MINUS, 120.0),
        (Grade.C_PLUS, 180.0),
        (Grade.C, 250.0),
        (Grade.C_MINUS, 350.0),
        (Grade.D, 500.0),
        (Grade.F, float("inf")),
    ],
    TaskType.BIOMETRIC: [
        # EER: lower = better
        (Grade.A_PLUS, 0.01),
        (Grade.A, 0.03),
        (Grade.A_MINUS, 0.05),
        (Grade.B_PLUS, 0.08),
        (Grade.B, 0.10),
        (Grade.B_MINUS, 0.15),
        (Grade.C_PLUS, 0.20),
        (Grade.C, 0.25),
        (Grade.C_MINUS, 0.30),
        (Grade.D, 0.40),
        (Grade.F, float("inf")),
    ],
    TaskType.GAZE: [
        # MAE in degrees: lower = better
        (Grade.A_PLUS, 0.5),
        (Grade.A, 1.0),
        (Grade.A_MINUS, 1.5),
        (Grade.B_PLUS, 2.5),
        (Grade.B, 4.0),
        (Grade.B_MINUS, 6.0),
        (Grade.C_PLUS, 9.0),
        (Grade.C, 12.0),
        (Grade.C_MINUS, 16.0),
        (Grade.D, 22.0),
        (Grade.F, float("inf")),
    ],
    TaskType.REGRESSION: [
        # Generic MAE — same as gaze but wider range
        (Grade.A_PLUS, 0.01),
        (Grade.A, 0.05),
        (Grade.A_MINUS, 0.10),
        (Grade.B_PLUS, 0.20),
        (Grade.B, 0.35),
        (Grade.B_MINUS, 0.50),
        (Grade.C_PLUS, 0.70),
        (Grade.C, 1.00),
        (Grade.C_MINUS, 1.50),
        (Grade.D, 2.50),
        (Grade.F, float("inf")),
    ],
}

# Tasks where lower = better (built-in defaults; can be overridden via GradeConfig)
_LOWER_BETTER: frozenset[TaskType] = frozenset(
    {
        TaskType.NLP,
        TaskType.BIOMETRIC,
        TaskType.GAZE,
        TaskType.REGRESSION,
    }
)

# Map of normalised string variants → canonical Grade label for YAML keys.
# Allows both "A+" (direct) and "A_PLUS" / "APLUS" (code-friendly) forms.
_LABEL_ALIASES: dict[str, str] = {
    "A_PLUS": "A+",
    "APLUS": "A+",
    "A_MINUS": "A-",
    "AMINUS": "A-",
    "B_PLUS": "B+",
    "BPLUS": "B+",
    "B_MINUS": "B-",
    "BMINUS": "B-",
    "C_PLUS": "C+",
    "CPLUS": "C+",
    "C_MINUS": "C-",
    "CMINUS": "C-",
}


def is_lower_better(task: TaskType, config: GradeConfig | None = None) -> bool:
    """Whether *task*'s primary metric improves by decreasing (loss/MAE/EER/…).

    A ``GradeConfig`` override takes precedence over the built-in default set.
    """
    if config is not None:
        override = config.get_lower_better(task)
        if override is not None:
            return override
    return task in _LOWER_BETTER


def _dict_to_thresholds(
    d: dict[str, float], *, lower_better: bool = False
) -> list[tuple[Grade, float]]:
    """Convert ``{grade_label: threshold}`` dict to sorted internal list.

    For *higher-is-better* tasks the list is sorted **descending** so the best
    grade (highest threshold) is checked first.  For *lower-is-better* tasks
    it is sorted **ascending** so the strictest threshold (lowest value) is
    checked first — mirroring the layout of ``_DEFAULT_THRESHOLDS``.
    """
    result: list[tuple[Grade, float]] = []
    for raw_label, threshold in d.items():
        canonical = _LABEL_ALIASES.get(raw_label.upper(), raw_label)
        result.append((Grade(canonical), threshold))
    reverse = not lower_better  # descending for higher-is-better, ascending for lower
    return sorted(result, key=lambda x: x[1], reverse=reverse)


def compute_grade(
    task: TaskType,
    primary_value: float,
    custom_thresholds: dict[str, float] | None = None,
    config: GradeConfig | None = None,
) -> Grade:
    """Return the letter grade for the current primary metric value.

    Priority for thresholds (highest → lowest):

    1. *custom_thresholds* — explicit dict passed by the caller.
    2. *config* — :class:`GradeConfig` loaded from ``.epochix.yaml``.
    3. Built-in *_DEFAULT_THRESHOLDS*.

    The lower-better direction is taken from *config.get_lower_better(task)*
    when a config is supplied, falling back to the built-in ``_LOWER_BETTER``
    set.
    """
    thresholds = _DEFAULT_THRESHOLDS.get(task, _DEFAULT_THRESHOLDS[TaskType.CLASSIFICATION])

    # Determine lower-better direction first — config override takes precedence
    if config is not None:
        lb_override = config.get_lower_better(task)
        lower_better = lb_override if lb_override is not None else task in _LOWER_BETTER
    else:
        lower_better = task in _LOWER_BETTER

    if custom_thresholds:
        thresholds = _dict_to_thresholds(custom_thresholds, lower_better=lower_better)
    elif config is not None:
        cfg_thresholds = config.get_thresholds(task)
        if cfg_thresholds:
            thresholds = _dict_to_thresholds(cfg_thresholds, lower_better=lower_better)

    for grade, threshold in thresholds:
        if lower_better:
            if primary_value <= threshold:
                return grade
        else:
            if primary_value >= threshold:
                return grade

    return Grade.F
