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

CatBoost had never been run at all, and its classifier was told backwards:

* **An AUC was called a loss.** CatBoost prints "test: 0.9790356" with the
  metric's name nowhere on the line; read as a loss, an AUC climbing from 0.979
  to 0.992 was narrated "past its best".
* **Its timing was a metric.** "total: 137ms<TAB>remaining: 8.11s" became a
  series called "ms<TAB>remaining" on every row.
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
CB_CLASSIFIER = LOGS / "catboost_real_classifier.log"
CB_REGRESSOR = LOGS / "catboost_real_regressor.log"
CB_TWO_EVAL_SETS = LOGS / "catboost_real_two_eval_sets.log"
CB_NO_EVAL_SET = LOGS / "catboost_real_no_eval_set.log"
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


def test_a_catboost_auc_is_told_as_a_rising_score() -> None:
    text = CB_CLASSIFIER.read_text(encoding="utf-8")
    assert "learn:" not in text, "the fixture should print the eval set alone"
    run, frames = _told(CB_CLASSIFIER)
    assert run.parser_used == "boosting"
    assert run.primary_metric == "val_score"
    assert [f.epoch for f in frames] == [float(r) for r in range(60)]
    assert frames[0].primary_metric_value == pytest.approx(0.9790356)
    assert frames[-1].primary_metric_value == pytest.approx(0.9924528)
    assert not any("past its best" in (f.narrative or "") for f in frames)


@pytest.mark.parametrize("log", [CB_CLASSIFIER, CB_REGRESSOR], ids=lambda p: p.name)
def test_catboost_s_timing_and_summary_are_not_metrics(log: Path) -> None:
    text = log.read_text(encoding="utf-8")
    assert "remaining:" in text and "bestTest =" in text, "the fixture lost its tail"
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("b", str(log)), run_id="b", store=store, hub=Hub())
    )
    keys = {e.canonical_key for e in store.get_metric_events("b")}
    assert keys <= {"train_loss", "val_loss", "val_score"}, keys


def test_catboost_s_overfitting_detector_run_ends_where_it_stopped() -> None:
    text = CB_REGRESSOR.read_text(encoding="utf-8")
    assert "Stopped by overfitting detector" in text
    run, frames = _told(CB_REGRESSOR)
    assert run.primary_metric == "val_loss"
    # Rounds 0-56: the best was round 41, and the detector waited 15 more.
    assert [f.epoch for f in frames] == [float(r) for r in range(57)]
    assert frames[-1].primary_metric_value == pytest.approx(55.4836303)


def test_catboost_with_two_eval_sets_is_told_on_the_one_it_tracks() -> None:
    text = CB_TWO_EVAL_SETS.read_text(encoding="utf-8")
    assert "test1:" in text and "bestTest = 57.20200783" in text, "the fixture changed"
    run, frames = _told(CB_TWO_EVAL_SETS)
    # The second set is the one CatBoost's best (and overfitting detector)
    # follows; read as a score off the first, this run was graded F.
    assert run.primary_metric == "val_loss"
    assert [f.epoch for f in frames] == [float(r) for r in range(40)]
    assert frames[-1].primary_metric_value == pytest.approx(57.2020078)
    assert "F" not in {f.grade.value for f in frames}


def test_catboost_without_an_eval_set_is_told_on_its_training_loss() -> None:
    assert "test:" not in CB_NO_EVAL_SET.read_text(encoding="utf-8")
    run, frames = _told(CB_NO_EVAL_SET)
    assert run.primary_metric == "train_loss"
    assert [f.epoch for f in frames] == [float(r) for r in range(40)]
    assert frames[-1].primary_metric_value == pytest.approx(0.0383251)
