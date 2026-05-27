"""Metaphor-pack YAML loader.

Third-party packages provide domain-specific :class:`~epochix.models.MetaphorCard`
templates by pointing to a YAML file via the ``epochix.metaphor_packs`` entry-point
group.

YAML schema::

    task: biometric          # task type key (must match epochix.enums.TaskType)
    cards:
      awakening:
        - title: "Identity awakens"
          body: "The system sees everyone as the same. EER: {value}."
          icon: "👁️"
          color: "#6366f1"   # optional hex colour
      learning:
        - title: "Faces take shape"
          body: "Broad identity clusters are forming. EER: {value}."
          icon: "🔍"

Supported placeholder tokens (same as narrative templates):
    {epoch}     — current epoch number
    {value}     — primary metric value (4 decimal places)
    {value_pct} — primary metric as percentage
    {delta}     — delta from previous epoch (signed)
"""
from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path
from typing import Any

from epochix.models import MetaphorCard

logger = logging.getLogger(__name__)

# Registry: task_key → phase_key → list[MetaphorCard]
_metaphor_registry: dict[str, dict[str, list[MetaphorCard]]] = {}
_loaded = False


def _load_metaphor_plugins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    eps = importlib.metadata.entry_points(group="epochix.metaphor_packs")
    for ep in eps:
        try:
            value = ep.load()
            # Entry point value should be a Path or string path to a YAML file
            yaml_path = Path(str(value))
            _load_yaml_pack(yaml_path, source=ep.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load metaphor pack %r: %s", ep.name, exc)


def load_yaml_pack(path: str | Path) -> None:
    """Public API: manually load a metaphor pack from a YAML file path."""
    _load_yaml_pack(Path(path), source=str(path))


def _load_yaml_pack(path: Path, *, source: str) -> None:
    """Parse a metaphor pack YAML file and register its cards."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "PyYAML is required for metaphor packs. "
            "Install with: pip install pyyaml"
        ) from None

    if not path.exists():
        logger.warning("Metaphor pack file not found: %s (source: %s)", path, source)
        return

    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    task_key: str = str(data.get("task", "custom")).lower()
    cards_data: dict[str, list[dict[str, str]]] = data.get("cards", {})

    registered_phases = 0
    for phase_key, card_list in cards_data.items():
        if not isinstance(card_list, list):
            logger.warning(
                "Metaphor pack %r phase %r: expected list, got %s",
                source, phase_key, type(card_list).__name__,
            )
            continue
        cards = [
            MetaphorCard(
                title=str(c.get("title", "")),
                body=str(c.get("body", "")),
                icon=str(c.get("icon", "")),
                color=str(c.get("color", "")),
            )
            for c in card_list
            if isinstance(c, dict)
        ]
        if cards:
            _metaphor_registry.setdefault(task_key, {})[phase_key] = cards
            registered_phases += 1

    logger.info(
        "Loaded metaphor pack %r: task=%s, %d phases",
        source, task_key, registered_phases,
    )


def get_metaphor_cards(
    task_key: str,
    phase_key: str,
    *,
    epoch: float | None = None,
    value: float = 0.0,
    delta: float = 0.0,
) -> list[MetaphorCard]:
    """Return rendered metaphor cards for the given task + phase.

    Returns an empty list if no pack is registered for this task/phase combo.
    Placeholder tokens in ``body`` are expanded before returning.
    """
    task_data = _metaphor_registry.get(task_key.lower(), {})
    raw_cards = task_data.get(phase_key.lower(), [])

    if not raw_cards:
        return []

    epoch_str = str(int(epoch)) if epoch is not None else "?"
    delta_str = f"{delta:+.4f}" if delta != 0 else "0"

    rendered: list[MetaphorCard] = []
    for card in raw_cards:
        body = (
            card.body
            .replace("{epoch}", epoch_str)
            .replace("{value}", f"{value:.4f}")
            .replace("{value_pct}", f"{value * 100:.1f}%")
            .replace("{delta}", delta_str)
        )
        rendered.append(MetaphorCard(
            title=card.title,
            body=body,
            icon=card.icon,
            color=card.color,
        ))
    return rendered


def list_packs() -> dict[str, list[str]]:
    """Return a mapping of task_key → registered phase keys."""
    return {task: list(phases.keys()) for task, phases in _metaphor_registry.items()}
