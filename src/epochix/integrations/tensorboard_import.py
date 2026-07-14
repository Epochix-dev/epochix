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
import re
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
        _open_dashboard(port, runs[0].id)

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


# TensorBoard tags are conventionally "Metric/split" ("Loss/train") or
# "split/metric" ("train/loss"). The normalizer wants "train_loss" —
# "loss_train" is not recognised and lands as an unusable `custom` metric.
_SPLITS = {
    "train": "train",
    "training": "train",
    "val": "val",
    "valid": "val",
    "validation": "val",
    "eval": "val",
    "test": "test",
}


def _tag_to_key(tag: str) -> str:
    """`Loss/train` → `train_loss`, `Accuracy/val` → `val_accuracy`, `lr` → `lr`."""
    parts = [p for p in re.split(r"[/\s]+", tag.strip()) if p]
    lowered = [p.lower() for p in parts]
    # YOLO and friends prefix everything with a bare "metrics/" namespace.
    if len(lowered) > 1 and lowered[0] == "metrics":
        lowered = lowered[1:]

    for i, part in enumerate(lowered):
        if part in _SPLITS:
            rest = lowered[:i] + lowered[i + 1 :]
            split = _SPLITS[part]
            return "_".join([split, *rest]) if rest else split
    return "_".join(lowered)


def _import_one(event_dir: Path, *, name: str, port: int) -> Any:  # noqa: ANN401
    """Import a single TensorBoard log directory into epochix."""
    events = list(_read_scalar_events(event_dir))
    if not events:
        logger.warning("No scalar events found in %s", event_dir)
        return None

    from epochix.config import get_settings
    from epochix.sdk.live_reporter import LiveReporter
    from epochix.store.sqlite_store import RunStore

    # Group by step. EventAccumulator yields tag-by-tag (every loss, THEN every
    # accuracy), and the step used to be discarded entirely — so the story
    # engine saw a scrambled, epoch-less stream and produced ZERO frames.
    by_step: dict[int, dict[str, float]] = {}
    for step, tag, value in events:
        by_step.setdefault(step, {})[_tag_to_key(tag)] = value

    reporter = LiveReporter(name=name, port=port, open_browser=False)
    with reporter:
        for step in sorted(by_step):
            # TB's global_step is the only epoch signal there is; a run logged
            # per-batch will simply have many "epochs".
            reporter.log(epoch=float(step), **by_step[step])

    run_id = reporter._run_id  # noqa: SLF001
    return RunStore(db_path=get_settings().db).get_run(run_id)


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
