"""epochix plugin system.

Third-party packages integrate by declaring Python entry points in one of two
groups:

    epochix.parsers    — custom log format parsers
    epochix.exporters  — custom export formats

Parsers are loaded by ``parsers.registry`` on the first ``detect_parser``
call; exporters by ``exporter_registry`` the first time a format that is not
built in is asked for.

Two more groups were documented, ``epochix.metaphor_packs`` and
``epochix.tasks``, and removed on 2026-11-18 having never been read: an
installed pack changed no card and an installed task changed no grade. A
pack's cards were free text beside the grade, which epochix's own words are
not allowed to be, and a task plugin would have graded against a closed
``TaskType`` in one engine and not the other. A task's thresholds are set in
the project's ``.epochix.yaml``, which both engines read.

Example ``pyproject.toml`` for a plugin package::

    [project.entry-points."epochix.parsers"]
    fairseq = "epochix_fairseq.parser:FairseqParser"

    [project.entry-points."epochix.exporters"]
    latex = "epochix_latex.exporter:EXPORTER"
"""

from __future__ import annotations


def reset_plugins() -> None:
    """Forget every loaded exporter plugin (for testing only)."""
    from epochix.plugins import exporter_registry

    exporter_registry._exporter_registry.clear()
    exporter_registry._exporter_sources.clear()
    exporter_registry._loaded = False
