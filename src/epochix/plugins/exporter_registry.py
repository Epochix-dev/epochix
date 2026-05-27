"""Custom exporter registry.

Third-party packages register additional export formats via the
``epochix.exporters`` entry-point group.

The entry point value must be a callable with the signature::

    def export(
        run: Run,
        frames: Sequence[StoryFrame],
        events: Sequence[MetricEvent],
        output_path: str,
    ) -> None: ...

or a class with a ``__call__`` method with the same signature.

Example::

    # my_package/my_exporter.py
    from pathlib import Path
    from epochix.models import Run, StoryFrame, MetricEvent
    from typing import Sequence

    def export_latex(
        run: Run,
        frames: Sequence[StoryFrame],
        events: Sequence[MetricEvent],
        output_path: str,
    ) -> None:
        Path(output_path).write_text("\\\\documentclass{article}\\n...")

    EXPORTER = export_latex

    # pyproject.toml:
    # [project.entry-points."epochix.exporters"]
    # latex = "my_package.my_exporter:EXPORTER"
"""
from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from epochix.models import MetricEvent, Run, StoryFrame

logger = logging.getLogger(__name__)

# Registry: format name → callable
_exporter_registry: dict[str, Callable[..., None]] = {}
_loaded = False


def _load_exporter_plugins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    eps = importlib.metadata.entry_points(group="epochix.exporters")
    for ep in eps:
        try:
            exporter = ep.load()
            if not callable(exporter):
                logger.warning(
                    "Exporter plugin %r: expected callable, got %s",
                    ep.name, type(exporter).__name__,
                )
                continue
            _exporter_registry[ep.name] = exporter
            logger.info("Registered exporter %r from plugin", ep.name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load exporter plugin %r: %s", ep.name, exc)


def register_exporter(name: str, fn: Callable[..., None]) -> None:
    """Manually register an exporter callable (bypasses entry points)."""
    if not callable(fn):
        raise TypeError(f"Exporter must be callable, got {type(fn).__name__}")
    _exporter_registry[name] = fn
    logger.info("Registered exporter %r manually", name)


def get_exporter(name: str) -> Callable[..., None] | None:
    """Look up a registered exporter by format name."""
    return _exporter_registry.get(name)


def list_exporters() -> list[str]:
    """Return names of all registered custom exporters."""
    return list(_exporter_registry.keys())


def run_exporter(
    name: str,
    run: Run,
    frames: Sequence[StoryFrame],
    events: Sequence[MetricEvent],
    output_path: str,
) -> None:
    """Invoke a named exporter; raises :class:`KeyError` if not registered."""
    fn = _exporter_registry.get(name)
    if fn is None:
        available = ", ".join(sorted(_exporter_registry)) or "(none)"
        raise KeyError(
            f"No exporter registered for format {name!r}. Available: {available}"
        )
    fn(run, frames, events, output_path)


def _reset() -> None:  # pragma: no cover
    """Reset for testing."""
    global _loaded
    _exporter_registry.clear()
    _loaded = False


# ── Type alias exported for plugin authors ────────────────────────────────────

ExporterFn = Any  # Callable[[Run, Sequence[StoryFrame], Sequence[MetricEvent], str], None]
