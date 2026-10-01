"""Real XGBoost and LightGBM output (tests/fixtures/logs/boosting_real_source.py).

XGBoost read correctly. LightGBM did not, in three ways:

* **The story was told on the training score.** `AUC` was preferred to
  `val_AUC`, so a classifier at 0.984 on held-out data was narrated
  "AUC 1.0000".
* **A healthy run was reported as diverged at its first round.** LightGBM
  routinely warns "No further splits with positive gain, best gain: -inf";
  `gain: -inf` was taken for a metric that had become infinite.
* **The reprint of the best round was read as a new measurement.** After
  "Early stopping, best iteration is:" LightGBM prints that round again; a
  29-round run ended its story on round 19.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import Run, StoryFrame
from epochix.parsers.base import ParserContext
from epochix.parsers.boosting import BoostingParser
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import _PREFERRED_KEYS_FOR_TASK

LOGS = Path(__file__).resolve().parents[1] / "fixtures" / "logs"
LGB_CLASSIFIER = LOGS / "lightgbm_real_classifier.log"
LGB_EARLY_STOP = LOGS / "lightgbm_real_early_stopping.log"
XGB_CLASSIFIER = LOGS / "xgboost_real_classifier.log"


def _told(log: Path) -> tuple[Run, list[StoryFrame]]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("b", str(log)), run_id="b", store=store, hub=Hub())
    )
    return run, store.get_story_frames("b")


def test_lightgbm_is_told_on_its_validation_score() -> None:
    run, frames = _told(LGB_CLASSIFIER)
    assert run.parser_used == "boosting"
    assert run.primary_metric == "val_AUC"
    assert {f.primary_metric for f in frames} == {"val_AUC"}
    assert [f.epoch for f in frames] == [float(r) for r in range(1, 61)]
    assert frames[0].primary_metric_value == pytest.approx(0.963103)
    assert frames[-1].primary_metric_value == pytest.approx(0.983648)


@pytest.mark.parametrize("log", [LGB_CLASSIFIER, LGB_EARLY_STOP], ids=lambda p: p.name)
def test_a_routine_lightgbm_warning_is_not_a_divergence(log: Path) -> None:
    assert "best gain: -inf" in log.read_text(encoding="utf-8"), "the fixture lost its warning"
    _, frames = _told(log)
    assert not [w for f in frames for w in f.warnings if w.kind == "divergence"]
    assert "F" not in {f.grade.value for f in frames}


def test_a_metric_that_does_go_infinite_is_still_caught(tmp_path: Path) -> None:
    lines = [f"[{r}]\tvalid_0's l2: {30 - r}.5" for r in range(1, 6)]
    lines.append("[6]\tvalid_0's l2: inf")
    log = tmp_path / "diverged.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _, frames = _told(log)
    assert [w.kind for f in frames for w in f.warnings] == ["divergence"]


def test_the_reprinted_best_round_is_not_a_new_reading() -> None:
    text = LGB_EARLY_STOP.read_text(encoding="utf-8")
    assert "Early stopping, best iteration is:" in text
    assert text.rstrip().splitlines()[-1].startswith("[19]"), "the fixture's reprint moved"
    _, frames = _told(LGB_EARLY_STOP)
    assert [f.epoch for f in frames] == [float(r) for r in range(1, 30)]
    assert frames[-1].primary_metric_value == pytest.approx(45.1215)


@pytest.mark.parametrize(
    "announcement",
    [
        "Early stopping, best iteration is:",
        "Did not meet early stopping. Best iteration is:",
        "Stopping. Best iteration:",
    ],
)
def test_every_library_s_announcement_skips_one_row(announcement: str) -> None:
    parser, ctx = BoostingParser(), ParserContext(run_id="t")
    assert parser.parse_line("[7]\tvalid_0's l2: 3.1", ctx)
    assert parser.parse_line(announcement, ctx) == []
    assert parser.parse_line("[5]\tvalid_0's l2: 2.9", ctx) == [], "the reprint was read"
    # Only that one row: a run that resumes is read again.
    assert parser.parse_line("[8]\tvalid_0's l2: 3.0", ctx)


def test_xgboost_reads_both_eval_sets() -> None:
    run, frames = _told(XGB_CLASSIFIER)
    assert run.primary_metric == "val_log_loss"
    assert [f.epoch for f in frames] == [float(r) for r in range(60)]
    assert frames[-1].primary_metric_value == pytest.approx(0.15139)


def test_no_task_prefers_a_training_metric_to_its_validation_twin() -> None:
    """The story's metric is the first preferred key seen, so the order decides
    which split a run is told on when it logs both."""
    inverted = [
        (task.value, key)
        for task, keys in _PREFERRED_KEYS_FOR_TASK.items()
        for i, key in enumerate(keys)
        if not key.startswith("val_") and f"val_{key}" in keys[i:]
    ]
    assert not inverted, inverted
