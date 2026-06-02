"""TensorBoard event-file importer.

Reads `events.out.tfevents.*` files from a TensorBoard ``logdir`` and
converts the scalar summaries into epochix :class:`~epochix.models.MetricEvent`
objects that are fed through the standard pipeline.

Usage::

    # CLI
    epochix import-tensorboard ./runs/

    # Python
    from epochix.integrations.tensorboard_import import import_tensorboard
    runs = import_tensorboard("./runs/", port=7860)

``tensorboard`` (or ``tensorflow``) is an optional dependency — the module
imports it lazily.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def import_tensorboard(
    logdir: str | Path,
    *,
    port: int = 7860,
    open_browser: bool = True,
    run_name: str | None = None,
) -> list[Any]:
    """Import all scalar events from a TensorBoard logdir.

    Parameters
    ----------
    logdir:
        Path to the TensorBoard log directory (contains ``events.out.tfevents.*``).
    port:
        Port of the epochix server to push events to.
    open_browser:
        Open the dashboard after importing.
    run_name:
        Human-readable name for the imported run.

    Returns
    -------
    list
        The imported :class:`~epochix.models.Run` objects (one per sub-directory).
    """
    logdir = Path(logdir)
    runs = []

    for event_dir in _find_event_dirs(logdir):
        name = run_name or event_dir.name
        logger.info("Importing TensorBoard events from %s", event_dir)
        try:
            run = _import_one(event_dir, name=name, port=port)
            if run:
                runs.append(run)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s: %s", event_dir, exc)

    if open_browser and runs:
        _open_dashboard(port, runs[0])

    return runs


# ── Internal ──────────────────────────────────────────────────────────────────


def _find_event_dirs(root: Path) -> list[Path]:
    """Find all directories that contain TensorBoard event files."""
    dirs: list[Path] = []
    for p in root.rglob("events.out.tfevents.*"):
        if p.parent not in dirs:
            dirs.append(p.parent)
    if not dirs and any(root.glob("events.out.tfevents.*")):
        dirs.append(root)
    return dirs or [root]


def _import_one(event_dir: Path, *, name: str, port: int) -> Any:  # noqa: ANN401
    """Import a single TensorBoard log directory into epochix."""
    events = list(_read_scalar_events(event_dir))
    if not events:
        logger.warning("No scalar events found in %s", event_dir)
        return None

    from epochix.sdk.live_reporter import LiveReporter

    reporter = LiveReporter(name=name, port=port, open_browser=False)
    with reporter:
        for _step, tag, value in events:
            # Map TensorBoard tag to a canonical-ish metric name
            key = tag.replace("/", "_").replace(" ", "_").lower()
            reporter.log(**{key: value})

    return reporter._run_id  # noqa: SLF001


def _read_scalar_events(event_dir: Path) -> Iterator[tuple[int, str, float]]:
    """Yield (step, tag, value) for all scalar summaries in the directory."""
    try:
        from tensorboard.backend.event_processing.event_accumulator import (  # type: ignore[import-not-found]
            EventAccumulator,
        )
    except ImportError:
        raise ImportError(
            "tensorboard is required for TensorBoard import. Install with: pip install tensorboard"
        ) from None

    ea = EventAccumulator(str(event_dir))
    ea.Reload()

    for tag in ea.Tags().get("scalars", []):
        for event in ea.Scalars(tag):
            yield event.step, tag, event.value


def _open_dashboard(port: int, run_id: str) -> None:
    import webbrowser

    webbrowser.open(f"http://127.0.0.1:{port}/v/{run_id}")
