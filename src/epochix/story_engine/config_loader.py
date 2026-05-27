"""Loader for .epochix.yaml grade threshold configuration.

Users can place a ``.epochix.yaml`` in their project root (or
``~/.epochix/.epochix.yaml`` for per-user defaults) to override
the built-in grade thresholds that epochix uses when scoring runs.

Search order when no explicit path is given:

1. Current working directory.
2. Each parent directory, up to the filesystem root.
3. ``~/.epochix/.epochix.yaml``.

Example ``.epochix.yaml``::

    version: 1

    grade_thresholds:
      classification:
        "A+": 0.97
        A:    0.92
        "A-": 0.88
        "B+": 0.83
        B:    0.76
        "B-": 0.70
        "C+": 0.63
        C:    0.55
        "C-": 0.48
        D:    0.40
        F:    0.0

    lower_better:
      nlp: true        # perplexity — lower is better

"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from epochix.enums import TaskType

_CONFIG_FILENAME = ".epochix.yaml"


@dataclass
class GradeConfig:
    """Parsed grade threshold configuration from ``.epochix.yaml``."""

    #: Mapping of task key → {grade label → threshold value}.
    grade_thresholds: dict[str, dict[str, float]] = field(default_factory=dict)

    #: Optional per-task override: True when lower metric values are better.
    lower_better_override: dict[str, bool] = field(default_factory=dict)

    def get_thresholds(self, task: TaskType) -> dict[str, float] | None:
        """Return the threshold dict for *task*, or ``None`` if not configured."""
        return self.grade_thresholds.get(task.value)

    def get_lower_better(self, task: TaskType) -> bool | None:
        """Return the lower-better override for *task*, or ``None`` to use the default."""
        return self.lower_better_override.get(task.value)


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

    # Per-user fallback
    home_config = Path.home() / ".epochix" / _CONFIG_FILENAME
    if home_config.is_file():
        return home_config

    return None


def load_grade_config(path: Path | None = None) -> GradeConfig | None:
    """Load a :class:`GradeConfig` from *path*, or auto-discover if ``None``.

    Returns ``None`` when:

    * No config file can be found.
    * PyYAML is not installed (soft dependency).
    * The file cannot be parsed as valid YAML.

    In all these cases the caller should fall back to built-in defaults.
    """
    if path is None:
        path = find_config_file()

    if path is None or not path.is_file():
        return None

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None  # PyYAML is optional — fail silently

    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None  # malformed YAML — don't crash; use defaults

    if not isinstance(raw, dict):
        return None

    config = GradeConfig()

    thresholds_raw = raw.get("grade_thresholds", {})
    if isinstance(thresholds_raw, dict):
        for task_key, grade_map in thresholds_raw.items():
            if isinstance(grade_map, dict):
                config.grade_thresholds[str(task_key)] = {
                    str(k): float(v) for k, v in grade_map.items()
                }

    lower_better_raw = raw.get("lower_better", {})
    if isinstance(lower_better_raw, dict):
        for task_key, flag in lower_better_raw.items():
            config.lower_better_override[str(task_key)] = bool(flag)

    return config
