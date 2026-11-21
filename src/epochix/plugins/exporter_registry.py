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

An installed exporter is used by ``epochix export <run-id> --format latex``,
by ``epochix run --export latex``, and by the server at
``GET /api/export/<run-id>/latex``, all through :func:`export_with_plugin`.
The names of the built-in formats are taken: a plugin cannot replace them.

The group was documented, and loaded by nothing, until 2026-11-18: the CLI
answered "Unknown export format" for an installed plugin's format.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from epochix.models import MetricEvent, Run, StoryFrame
    from epochix.store.sqlite_store import RunStore

logger = logging.getLogger(__name__)

#: Formats epochix writes itself. A plugin of the same name is not loaded.
BUILTIN_FORMATS: tuple[str, ...] = ("html", "pdf", "md", "json", "gif")

# Registry: format name → callable
_exporter_registry: dict[str, Callable[..., None]] = {}
# Format name → the distribution that installed it, for error messages.
_exporter_sources: dict[str, str] = {}
_loaded = False


class ExporterFailed(RuntimeError):
    """A plugin exporter raised, or returned without writing its file."""


def _load_exporter_plugins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    eps = importlib.metadata.entry_points(group="epochix.exporters")
    for ep in eps:
        if ep.name in BUILTIN_FORMATS:
            logger.warning(
                "Exporter plugin %r not loaded: %r is a built-in format", ep.value, ep.name
            )
            continue
        try:
            exporter = ep.load()
            if not callable(exporter):
                logger.warning(
                    "Exporter plugin %r: expected callable, got %s",
                    ep.name,
                    type(exporter).__name__,
                )
                continue
            _exporter_registry[ep.name] = exporter
            dist = getattr(ep, "dist", None)
            _exporter_sources[ep.name] = str(dist.name) if dist is not None else ep.value
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
        raise KeyError(f"No exporter registered for format {name!r}. Available: {available}")
    fn(run, frames, events, output_path)


def plugin_exporter(name: str) -> Callable[..., None] | None:
    """The installed exporter for format *name*, or None.

    Loads the ``epochix.exporters`` entry points on first use. Always None
    for a built-in format.
    """
    _load_exporter_plugins()
    if name in BUILTIN_FORMATS:
        return None
    return _exporter_registry.get(name)


def plugin_format(name: str) -> str | None:
    """The installed plugin format equal to *name*, as its package declared it.

    The same text as *name*, but taken from the registry, not from the caller:
    a server builds a file name from it, and that name must come from what is
    installed, never from what a request said. None when no plugin provides
    *name*, and for a built-in format.
    """
    _load_exporter_plugins()
    for key in _exporter_registry:
        if key == name and key not in BUILTIN_FORMATS:
            return key
    return None


def available_formats() -> list[str]:
    """Every format that can be exported: the built-in ones, then plugins'."""
    _load_exporter_plugins()
    return [*BUILTIN_FORMATS, *sorted(n for n in _exporter_registry if n not in BUILTIN_FORMATS)]


def export_with_plugin(name: str, run_id: str, store: RunStore, output_path: Path) -> None:
    """Write run *run_id* to *output_path* with the installed exporter *name*.

    Raises :class:`KeyError` when no plugin provides *name*, ``ValueError``
    for an unknown run, and :class:`ExporterFailed` when the exporter raises
    or returns without having written *output_path*: an export that wrote
    nothing must not be reported as written.
    """
    fn = plugin_exporter(name)
    if fn is None:
        raise KeyError(name)
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")
    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)
    source = _exporter_sources.get(name, "a plugin")

    def _stamp() -> tuple[int, int] | None:
        try:
            st = output_path.stat()
        except OSError:
            return None
        return (st.st_size, st.st_mtime_ns)

    before = _stamp()
    try:
        fn(run, frames, events, str(output_path))
    except Exception as exc:
        raise ExporterFailed(
            f"The {name!r} exporter (from {source}) failed: {type(exc).__name__}: {exc}"
        ) from exc
    after = _stamp()
    if after is None or after == before:
        raise ExporterFailed(
            f"The {name!r} exporter (from {source}) returned without writing {output_path}."
        )


def _reset() -> None:  # pragma: no cover
    """Reset for testing."""
    global _loaded
    _exporter_registry.clear()
    _exporter_sources.clear()
    _loaded = False


# ── Type alias exported for plugin authors ────────────────────────────────────

ExporterFn = Any  # Callable[[Run, Sequence[StoryFrame], Sequence[MetricEvent], str], None]
