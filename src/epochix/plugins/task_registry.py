"""Custom task-type registry.

Third-party packages can register new task types — complete with grade thresholds,
primary metric name, and lower-is-better flag — via the ``epochix.tasks``
entry-point group.

The entry point value must be a :class:`TaskDefinition` instance or a dict
conforming to the same structure::

    # my_pack/task.py
    from epochix.plugins.task_registry import TaskDefinition

    TASK_DEFINITION = TaskDefinition(
        key="audio",
        display_name="Audio / Speech",
        primary_metric="word_error_rate",
        lower_better=True,
        grade_thresholds={
            "A+": 0.03,  # WER ≤ 3% → A+
            "A":  0.05,
            "A-": 0.08,
            "B+": 0.12,
            "B":  0.18,
            "B-": 0.25,
            "C+": 0.35,
            "C":  0.50,
            "C-": 0.65,
            "D":  0.80,
            "F":  float("inf"),
        },
    )

    # pyproject.toml:
    # [project.entry-points."epochix.tasks"]
    # audio = "my_pack.task:TASK_DEFINITION"
"""
from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Registry: task key → TaskDefinition
_task_registry: dict[str, TaskDefinition] = {}
_loaded = False


@dataclass
class TaskDefinition:
    """Full specification of a custom task type."""

    key: str
    """Unique task identifier (lowercase, no spaces)."""

    display_name: str
    """Human-readable name shown in the UI."""

    primary_metric: str
    """Canonical key of the primary metric (e.g. ``word_error_rate``)."""

    lower_better: bool = False
    """Whether lower values are better for the primary metric."""

    grade_thresholds: dict[str, float] = field(default_factory=dict)
    """Mapping of grade label to threshold value.

    For lower-is-better tasks, each threshold is the *maximum* value for that
    grade.  For higher-is-better tasks it is the *minimum*.
    """

    metric_aliases: list[str] = field(default_factory=list)
    """Alternative canonical keys that map to this task (used for auto-detection)."""


def _load_task_plugins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    eps = importlib.metadata.entry_points(group="epochix.tasks")
    for ep in eps:
        try:
            value = ep.load()
            _register_task_value(value, source=ep.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load task plugin %r: %s", ep.name, exc)


def _register_task_value(value: object, *, source: str) -> None:
    """Accept either a TaskDefinition or a plain dict."""
    if isinstance(value, TaskDefinition):
        definition = value
    elif isinstance(value, dict):
        try:
            definition = TaskDefinition(**value)
        except TypeError as exc:
            logger.warning("Task plugin %r: invalid dict schema: %s", source, exc)
            return
    else:
        logger.warning(
            "Task plugin %r: expected TaskDefinition or dict, got %s",
            source, type(value).__name__,
        )
        return

    if not definition.key:
        logger.warning("Task plugin %r: missing required field 'key'", source)
        return

    _task_registry[definition.key] = definition
    logger.info("Registered custom task %r from plugin %r", definition.key, source)


def register_task(definition: TaskDefinition) -> None:
    """Manually register a custom task definition (bypasses entry points)."""
    _register_task_value(definition, source="manual")


def get_task(key: str) -> TaskDefinition | None:
    """Look up a registered custom task by key."""
    return _task_registry.get(key)


def list_tasks() -> list[TaskDefinition]:
    """Return all registered custom task definitions."""
    return list(_task_registry.values())
