"""epochix plugin system.

Third-party packages integrate by declaring Python entry points in one of four
groups:

    epochix.parsers         — custom log format parsers
    epochix.metaphor_packs  — domain-specific narrative metaphor cards (YAML)
    epochix.exporters       — custom export formats
    epochix.tasks           — custom task types with grade thresholds

Plugins are discovered lazily on first use via :func:`load_all_plugins`.

Example ``pyproject.toml`` for a plugin package::

    [project.entry-points."epochix.parsers"]
    fairseq = "epochix_fairseq.parser:FairseqParser"

    [project.entry-points."epochix.metaphor_packs"]
    biometric = "epochix_biometric:METAPHORS_YAML"

    [project.entry-points."epochix.exporters"]
    latex = "epochix_latex.exporter:EXPORTER"

    [project.entry-points."epochix.tasks"]
    audio = "epochix_audio.task:TASK_DEFINITION"
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_plugins_loaded = False


def load_all_plugins() -> None:
    """Discover and load every installed epochix plugin (idempotent)."""
    global _plugins_loaded
    if _plugins_loaded:
        return
    _plugins_loaded = True

    from epochix.plugins.exporter_registry import _load_exporter_plugins
    from epochix.plugins.metaphor_loader import _load_metaphor_plugins
    from epochix.plugins.task_registry import _load_task_plugins

    # parsers are loaded separately by parsers.registry on first detect_parser call
    _load_metaphor_plugins()
    _load_task_plugins()
    _load_exporter_plugins()


def reset_plugins() -> None:
    """Reset plugin state (for testing only)."""
    global _plugins_loaded
    _plugins_loaded = False

    from epochix.plugins import exporter_registry, metaphor_loader, task_registry

    metaphor_loader._metaphor_registry.clear()
    metaphor_loader._loaded = False
    task_registry._task_registry.clear()
    task_registry._loaded = False
    exporter_registry._exporter_registry.clear()
    exporter_registry._loaded = False
