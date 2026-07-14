"""The YOLO parser against a BYTE-EXACT capture of real ultralytics output.

The hand-written yolo fixtures are clean columnar tables. Real ultralytics is
not: every epoch row is prefixed with \r and an ANSI erase, and carries a tqdm
progress bar on the same physical line, redrawn many times:

    \r\x1b[K   1/3   0G  1.352  3.58  1.419  4  320:   0%|     | 0/2 ...
    \r\x1b[K   1/3   0G  1.352  3.58  1.419  4  320: 100%|#####| 2/2 ...

The file ingesters opened logs in universal-newline mode, which turns a lone \r
into a LINE BREAK — so every progress redraw became its own line and was parsed
as another epoch row. Each epoch's losses were recorded once per redraw.
_clean_line() has always known how to collapse \r to the final visible state; it
simply never saw one.

This affects any log with a progress bar — tqdm, YOLO, Keras verbose=1.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.enums import TaskType
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    pass

LOG = Path(__file__).parents[1] / "fixtures" / "logs" / "yolo_real_ultralytics.log"

# What the real run actually reported (ultralytics 8.4.55, coco8, 3 epochs).
EPOCHS = 3
FINAL_MAP50 = 0.688


def test_the_fixture_still_has_its_carriage_returns() -> None:
    """If git ever normalises this file the test below silently stops testing."""
    raw = LOG.read_bytes()
    assert b"\r" in raw, (
        "the real-YOLO fixture lost its carriage returns — check .gitattributes "
        "(tests/fixtures/logs/*.log must be -text)"
    )


def test_real_yolo_output_parses_without_duplicating_epochs(tmp_path: Path) -> None:
    db = str(tmp_path / "runs.db")
    run = parse(LOG, db=db, run_name="real-yolo")

    assert run.task_type == TaskType.DETECTION
    assert run.parser_used == "ultralytics_yolo"
    assert run.primary_metric == "mAP50"

    store = RunStore(db_path=db)
    metrics = store.get_metric_events(run.id)

    # One value per epoch. Each progress-bar redraw used to be re-parsed, so
    # these came out at 2x (or worse, depending on how often tqdm repainted).
    for key in ("box_loss", "cls_loss", "dfl_loss"):
        values = [m for m in metrics if m.canonical_key == key]
        assert len(values) == EPOCHS, (
            f"{key}: expected {EPOCHS} events (one per epoch), got {len(values)} "
            "— progress-bar redraws are being parsed as separate epochs again"
        )

    epochs = sorted({m.epoch for m in metrics if m.epoch is not None})
    assert epochs == [1.0, 2.0, 3.0], epochs

    # The detection metrics are real and land on the right epochs.
    maps = [m for m in metrics if m.canonical_key == "mAP50"]
    assert maps, "no mAP50 captured from a real detection run"
    assert max(m.value for m in maps) == pytest.approx(FINAL_MAP50, abs=1e-3)
    assert all(0.0 <= m.value <= 1.0 for m in maps)

    # The dashboard gets a story, and the frames carry real epochs.
    frames = store.get_story_frames(run.id)
    assert frames, "a real YOLO run produced no story frames"
    assert all(f.epoch is not None for f in frames)
