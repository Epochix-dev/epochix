"""Custom grade thresholds from ``.epochix.yaml``.

A project can replace the built-in letter-grade cut-offs. The file is looked
for in the directory epochix is run from, then each parent, then
``~/.epochix/.epochix.yaml``; ``EPOCHIX_GRADE_CONFIG`` names a file directly,
or turns the lookup off with ``off``.

This module existed, with tests, for a long time before anything called it:
the README told people to write the file and no run ever read one. It is read
by the pipeline and the server now (``active_grade_config``), and what an
entry applies to is spelled out here rather than left to fall out of the
grading code.

Example::

    version: 1

    grade_thresholds:
      classification:      # a task: applies to its accuracy
        "A+": 0.97
        A:    0.92
        B:    0.80
        C:    0.65
        D:    0.50
        F:    0.0
      val_f1:              # a metric: applies to that metric, in any task
        A: 0.90
        B: 0.75
        C: 0.60
        F: 0.0

    lower_better:
      custom: true         # a metric whose name does not say

An entry lists the lowest value that still earns each grade — or the highest,
for a metric where lower is better. The order of the numbers says which.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from epochix.enums import Grade, TaskType
from epochix.normalizer.canonical_keys import canonicalize_key

_CONFIG_FILENAME = ".epochix.yaml"

# Values of EPOCHIX_GRADE_CONFIG that mean "use the built-in thresholds".
_DISABLED = frozenset({"off", "none", "false", "no", "0"})

# Map of normalised string variants → canonical Grade label for YAML keys.
# Allows both "A+" (direct) and "A_PLUS" / "APLUS" (code-friendly) forms.
LABEL_ALIASES: dict[str, str] = {
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

# Best to worst. "I" is not a grade a threshold can earn.
_LABEL_ORDER: tuple[str, ...] = tuple(g.value for g in Grade if g is not Grade.INCOMPLETE)

# The metric a task's entry is written for. Its thresholds are numbers on that
# metric's scale and mean nothing on another: a `regression` entry holds error
# bands in the target's units, and applied to an R² it graded 0.99 a B.
#
# Mostly these are the metrics the built-in task bands grade. Two are not, on
# purpose. Regression and generative runs are graded on improvement by default,
# because the scale of an MAE or an FID is not knowable from a log — but a
# project that writes the bands down has just supplied it.
#
# A `custom` entry has no metric of its own: it applies to whatever the run is
# told by.
GOVERNED_METRICS: dict[TaskType, frozenset[str]] = {
    TaskType.CLASSIFICATION: frozenset({"val_accuracy", "accuracy"}),
    TaskType.DETECTION: frozenset({"mAP50"}),
    TaskType.SEGMENTATION: frozenset({"mIoU"}),
    TaskType.NLP: frozenset({"perplexity"}),
    TaskType.BIOMETRIC: frozenset({"EER"}),
    TaskType.GAZE: frozenset({"val_MAE", "MAE"}),
    TaskType.REGRESSION: frozenset({"val_MAE", "MAE"}),
    TaskType.GENERATIVE: frozenset({"fid"}),
}

_TASK_NAMES = frozenset(task.value for task in TaskType)


def bands_lower_better(bands: dict[str, float]) -> bool | None:
    """Which way *bands* run, read from their own order, or None if they do not say.

    ``A+: 0.01 … D: 2.5`` is an error, where lower is better; ``A+: 0.95 … D:
    0.5`` is a score. Taking the direction from the numbers means an entry
    cannot be applied upside down, whatever the metric is called.
    """
    ranked = _ranked(bands)
    finite = [value for _, value in ranked if math.isfinite(value)]
    if len(finite) < 2 or finite[0] == finite[-1]:
        return None
    return finite[0] < finite[-1]


def _ranked(bands: dict[str, float]) -> list[tuple[str, float]]:
    """*bands* as (label, value), best grade first."""
    canonical = {LABEL_ALIASES.get(label.upper(), label): value for label, value in bands.items()}
    return [(label, canonical[label]) for label in _LABEL_ORDER if label in canonical]


@dataclass
class GradeConfig:
    """Parsed grade threshold configuration from ``.epochix.yaml``."""

    #: Mapping of task key → {grade label → threshold value}.
    grade_thresholds: dict[str, dict[str, float]] = field(default_factory=dict)

    #: Optional per-task override: True when lower metric values are better.
    lower_better_override: dict[str, bool] = field(default_factory=dict)

    #: Mapping of canonical metric name → {grade label → threshold value}.
    metric_thresholds: dict[str, dict[str, float]] = field(default_factory=dict)

    #: The file this was read from, when it was read from one.
    source: Path | None = None

    #: What in the file could not be used, in words a person can act on.
    problems: list[str] = field(default_factory=list)

    def get_thresholds(self, task: TaskType) -> dict[str, float] | None:
        """Return the threshold dict for *task*, or ``None`` if not configured."""
        return self.grade_thresholds.get(task.value)

    def get_lower_better(self, task: TaskType) -> bool | None:
        """Return the lower-better override for *task*, or ``None`` to use the default."""
        return self.lower_better_override.get(task.value)

    def bands_for(self, task: TaskType, metric: str) -> dict[str, float] | None:
        """The thresholds this file sets for *metric* in a run of *task*, or None.

        An entry named after the metric wins. A task's entry applies only to
        the metric it is written for (``GOVERNED_METRICS``); a ``custom`` entry
        to whatever a custom run is told by.
        """
        own = self.metric_thresholds.get(metric)
        if own:
            return own
        entry = self.grade_thresholds.get(task.value)
        if not entry:
            return None
        if task is TaskType.CUSTOM or metric in GOVERNED_METRICS.get(task, frozenset()):
            return entry
        return None


def find_config_file(start: Path | None = None) -> Path | None:
    """Locate the nearest ``.epochix.yaml`` file.

    Walks up from *start* (defaults to ``Path.cwd()``), then checks
    ``~/.epochix/.epochix.yaml``.  Returns the first path found,
    or ``None``.
    """
    search_dir = (start or Path.cwd()).resolve()
    for directory in [search_dir, *search_dir.parents]:
        candidate = directory / _CONFIG_FILENAME
        if candidate.is_file():
            return candidate

    # Per-user fallback. A stripped environment (a service, a container, a
    # subprocess given no USERPROFILE) has no home to look in, and that must
    # not stop a run.
    try:
        home_config = Path.home() / ".epochix" / _CONFIG_FILENAME
    except RuntimeError:
        return None
    if home_config.is_file():
        return home_config

    return None


def _read(path: Path) -> tuple[GradeConfig | None, str | None]:
    """The config in *path*, or why there is none."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None, "PyYAML is not installed (pip install pyyaml)"

    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a bad file must not stop a run
        return None, f"it is not valid YAML ({type(exc).__name__})"

    if raw is None:
        return None, None  # empty, or every line a comment: nothing is set
    if not isinstance(raw, dict):
        return None, "its top level is not a mapping"

    config = GradeConfig(source=path)

    thresholds_raw = raw.get("grade_thresholds", {})
    if isinstance(thresholds_raw, dict):
        for name, grade_map in thresholds_raw.items():
            key = str(name)
            if not isinstance(grade_map, dict):
                continue
            bands = _bands(key, grade_map, config.problems)
            if not bands:
                continue
            if key.lower() in _TASK_NAMES:
                config.grade_thresholds[key.lower()] = bands
            else:
                config.metric_thresholds[canonicalize_key(key)] = bands

    lower_better_raw = raw.get("lower_better", {})
    if isinstance(lower_better_raw, dict):
        for task_key, flag in lower_better_raw.items():
            config.lower_better_override[str(task_key)] = bool(flag)

    return config, None


def _bands(key: str, grade_map: dict[Any, Any], problems: list[str]) -> dict[str, float]:
    """The usable thresholds in one entry; what is wrong with it goes in *problems*."""
    bands: dict[str, float] = {}
    for raw_label, raw_value in grade_map.items():
        label = str(raw_label)
        if LABEL_ALIASES.get(label.upper(), label) not in _LABEL_ORDER:
            problems.append(f"{key}: '{label}' is not a grade (use A+ … D, F)")
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            problems.append(f"{key}: the threshold for {label} is not a number")
            continue
        if math.isnan(value):
            problems.append(f"{key}: the threshold for {label} is not a number")
            continue
        bands[label] = value

    values = [value for _, value in _ranked(bands)]
    rising = all(a <= b for a, b in zip(values, values[1:], strict=False))
    falling = all(a >= b for a, b in zip(values, values[1:], strict=False))
    if not (rising or falling):
        problems.append(
            f"{key}: the thresholds are not in order from A+ to F, so the entry is not used"
        )
        return {}
    return bands


def load_grade_config(path: Path | None = None) -> GradeConfig | None:
    """Load a :class:`GradeConfig` from *path*, or auto-discover if ``None``.

    Returns ``None`` when:

    * No config file can be found.
    * PyYAML is not installed.
    * The file cannot be parsed as valid YAML, or sets nothing.

    In all these cases the caller should fall back to built-in defaults;
    :func:`config_error` says which it was.
    """
    if path is None:
        path = find_config_file()

    if path is None or not path.is_file():
        return None

    return _read(path)[0]


def config_error(path: Path) -> str | None:
    """Why the file at *path* cannot be used at all, or None if it can."""
    if not path.is_file():
        return "it does not exist"
    return _read(path)[1]


def configured_path() -> Path | None:
    """The thresholds file in effect for this process, or None.

    ``EPOCHIX_GRADE_CONFIG`` names one, or turns the lookup off; left unset,
    the nearest ``.epochix.yaml`` is used.
    """
    from epochix.config import get_settings

    setting = get_settings().grade_config.strip()
    if setting.lower() in _DISABLED:
        return None
    if setting:
        return Path(setting).expanduser()
    return find_config_file()


def active_grade_config() -> GradeConfig | None:
    """The thresholds a run started now is graded with, or None for the built-in ones."""
    path = configured_path()
    return load_grade_config(path) if path is not None else None
