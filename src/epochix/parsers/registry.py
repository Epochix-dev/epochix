from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from epochix.parsers.base import BaseParser

logger = logging.getLogger(__name__)

_registry: list[BaseParser] = []
_loaded_plugins = False

SNIFF_THRESHOLD = 0.3
# Larger window so verbose modern CLIs (ultralytics, lightning) whose preamble
# easily exceeds 50 lines (model summary table, AMP checks, dataset scan)
# still have training rows in the sample by the time we sniff.
SNIFF_SAMPLE_LINES = 200


def register_parser(cls: type) -> type:
    """Decorator: register a parser class into the global registry."""
    instance = cls()
    _registry.append(instance)
    _registry.sort(key=lambda p: -p.priority)
    return cls


def _load_plugins() -> None:
    global _loaded_plugins
    if _loaded_plugins:
        return
    _loaded_plugins = True
    eps = importlib.metadata.entry_points(group="epochix.parsers")
    for ep in eps:
        try:
            cls = ep.load()
            instance = cls()
            if instance not in _registry:
                _registry.append(instance)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load parser plugin %r: %s", ep.name, exc)
    _registry.sort(key=lambda p: -p.priority)


def detect_parser(sample_lines: list[str]) -> BaseParser:
    """Return the best-matching parser for the given sample lines.

    Falls back to the universal parser when all scores are below SNIFF_THRESHOLD.
    """
    _load_plugins()
    best_parser: BaseParser | None = None
    best_score = -1.0

    for parser in _registry:
        try:
            score = parser.sniff(sample_lines)
        except Exception:  # noqa: BLE001
            score = 0.0
        if score > best_score:
            best_score = score
            best_parser = parser

    if best_parser is None or best_score < SNIFF_THRESHOLD:
        # Guaranteed fallback: universal parser is always registered
        from epochix.parsers.universal import UniversalParser

        return UniversalParser()

    return best_parser


def get_registry() -> list[BaseParser]:
    _load_plugins()
    return list(_registry)
