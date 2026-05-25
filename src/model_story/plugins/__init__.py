"""model-story plugin system.

Third-party packages integrate by declaring Python entry points in one of four
groups:

    model_story.parsers         — custom log format parsers
    model_story.metaphor_packs  — domain-specific narrative metaphor cards (YAML)
    model_story.exporters       — custom export formats
    model_story.tasks           — custom task types with grade thresholds

Plugins are discovered lazily on first use via :func:`load_all_plugins`.

Example ``pyproject.toml`` for a plugin package::

    [project.entry-points."model_story.parsers"]
    fairseq = "model_story_fairseq.parser:FairseqParser"

    [project.entry-points."model_story.metaphor_packs"]
    biometric = "model_story_biometric:METAPHORS_YAML"

    [project.entry-points."model_story.exporters"]
    latex = "model_story_latex.exporter:EXPORTER"

    [project.entry-points."model_story.tasks"]
    audio = "model_story_audio.task:TASK_DEFINITION"
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_plugins_loaded = False


def load_all_plugins() -> None:
    """Discover and load every installed model-story plugin (idempotent)."""
    global _plugins_loaded
    if _plugins_loaded:
        return
    _plugins_loaded = True

    from model_story.plugins.exporter_registry import _load_exporter_plugins
    from model_story.plugins.metaphor_loader import _load_metaphor_plugins
    from model_story.plugins.task_registry import _load_task_plugins

    # parsers are loaded separately by parsers.registry on first detect_parser call
    _load_metaphor_plugins()
    _load_task_plugins()
    _load_exporter_plugins()


def reset_plugins() -> None:
    """Reset plugin state (for testing only)."""
    global _plugins_loaded
    _plugins_loaded = False

    from model_story.plugins import exporter_registry, metaphor_loader, task_registry

    metaphor_loader._metaphor_registry.clear()
    metaphor_loader._loaded = False
    task_registry._task_registry.clear()
    task_registry._loaded = False
    exporter_registry._exporter_registry.clear()
    exporter_registry._loaded = False
