"""F1 is graded on accuracy's bands — and every frame says how it was graded.

Two things that went together.

**F1.** It was graded on how far it had improved, so a run going 0.90 → 0.91
was a C-: the letter described how little the metric moved, beside a number
that reads as strong. Its floor does follow the class balance — but so does
accuracy's, and accuracy has always been graded on fixed bands with the card
saying the grade does not know the dataset. F1 now shares those bands. This is
a decision (2026-10-02), not a derivation; a project that knows its class
balance sets its own with a `val_f1` entry in `.epochix.yaml`.

**The basis.** The card under the grade named both ways a letter can be
reached, because a frame did not record which applied. `grade_basis` does:
"thresholds", "improvement", or None where there is no letter to explain.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epochix.enums import Grade, TaskType
from epochix.exporters.markdown_export import build_markdown
from epochix.i18n import t
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import MetricEvent, StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import StoryEngine
from epochix.story_engine.grade import (
    _DEFAULT_THRESHOLDS,
    _METRIC_THRESHOLDS,
    compute_grade,
    grade_by_trajectory,
    has_absolute_scale,
)

REPO = Path(__file__).resolve().parents[2]
LOGS = REPO / "tests" / "fixtures" / "logs"


def _event(key: str, value: float, epoch: float | None, seq: int) -> MetricEvent:
    return MetricEvent(
        run_id="r",
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=epoch,
        canonical_key=key,
        raw_key=key,
        value=value,
    )


def _frames(key: str, values: list[float]) -> list[StoryFrame]:
    engine = StoryEngine(run_id="r")
    frames: list[StoryFrame] = []
    for seq, value in enumerate(values, start=1):
        frames += engine.process_all(_event(key, value, epoch=float(seq), seq=seq))
    # Guard: an engine that emitted nothing would pass every "is not" below.
    assert frames, f"no frame emitted for {key} {values}"
    assert {f.primary_metric for f in frames} == {key}
    return frames


def _told(log: Path) -> list[StoryFrame]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("r", str(log)), run_id="r", store=store, hub=Hub())
    )
    return store.get_story_frames("r")


class TestF1SharesAccuracysBands:
    @pytest.mark.parametrize("metric", ["f1", "val_f1"])
    def test_the_bands_are_accuracy_s_not_a_copy_of_them(self, metric: str) -> None:
        """The same object: change accuracy's bands and F1's follow."""
        assert has_absolute_scale(metric)
        assert _METRIC_THRESHOLDS[metric] is _DEFAULT_THRESHOLDS[TaskType.CLASSIFICATION]

    @pytest.mark.parametrize("value", [0.99, 0.91, 0.84, 0.72, 0.61, 0.52, 0.31])
    def test_an_f1_gets_the_letter_that_accuracy_would(self, value: float) -> None:
        for task in TaskType:
            assert compute_grade(task, value, metric="val_f1") is compute_grade(
                TaskType.CLASSIFICATION, value
            ), task

    def test_a_strong_f1_that_barely_moved_is_not_a_c_minus(self) -> None:
        """The fault itself."""
        values = [0.90, 0.902, 0.905, 0.908, 0.91]
        assert grade_by_trajectory(values[0], values[-1], False) is Grade.C_MINUS
        assert _frames("val_f1", values)[-1].grade is Grade.A

    def test_a_large_improvement_does_not_buy_a_good_grade(self) -> None:
        """The other direction, so the test above cannot pass by always saying A."""
        values = [0.20, 0.30, 0.40, 0.50, 0.58]
        assert grade_by_trajectory(values[0], values[-1], False) is Grade.A_PLUS
        assert _frames("val_f1", values)[-1].grade is Grade.C_MINUS

    def test_pr_auc_is_still_graded_on_improvement(self) -> None:
        assert not has_absolute_scale("PR_AUC")
        frames = _frames("PR_AUC", [0.40, 0.55, 0.70, 0.80, 0.84])
        assert frames[-1].grade is grade_by_trajectory(0.40, 0.84, False)
        assert frames[-1].grade_basis == "improvement"


class TestEveryFrameSaysHowItWasGraded:
    def test_a_metric_with_bands_is_graded_on_thresholds(self) -> None:
        for key in ("val_accuracy", "val_AUC", "val_f1", "val_R2"):
            frames = _frames(key, [0.5, 0.6, 0.7, 0.8, 0.9])
            assert {f.grade_basis for f in frames} == {"thresholds"}, key

    def test_a_loss_is_graded_on_improvement_once_it_has_moved(self) -> None:
        engine = StoryEngine(run_id="r")
        frames: list[StoryFrame] = []
        seq = 0
        for epoch, (train, val) in enumerate([(1.0, 1.1), (0.7, 0.8), (0.5, 0.6)], start=1):
            for key, value in (("train_loss", train), ("val_loss", val)):
                seq += 1
                frames += engine.process_all(_event(key, value, float(epoch), seq))
        told = [f for f in frames if f.primary_metric == "val_loss"]
        assert told, "no frame was told on the loss"
        # One reading has nothing to measure improvement against.
        assert (told[0].grade, told[0].grade_basis) == (Grade.INCOMPLETE, None)
        assert {f.grade_basis for f in told[1:]} == {"improvement"}
        assert Grade.INCOMPLETE not in {f.grade for f in told[1:]}

    def test_the_basis_is_none_exactly_when_the_letter_is_i_or_a_divergence(self) -> None:
        """Across the whole corpus: no frame claims a basis it does not have."""
        checked = 0
        for log in sorted(LOGS.glob("*.log")):
            if log.stat().st_size == 0:
                continue
            for frame in _told(log):
                checked += 1
                diverged = any(w.kind == "divergence" for w in frame.warnings)
                if frame.grade is Grade.INCOMPLETE:
                    assert frame.grade_basis is None, (log.name, frame.epoch)
                elif frame.grade_basis is None:
                    assert frame.grade is Grade.F and diverged, (log.name, frame.epoch)
        assert checked > 500, "the corpus told too few frames for this to mean anything"

    def test_a_real_run_of_each_kind(self) -> None:
        keras = _told(REPO / "demo" / "keras_image_classifier.log")
        assert {f.grade_basis for f in keras} == {"thresholds"}
        xgboost = [f for f in _told(LOGS / "xgboost_real_classifier.log") if f.grade_basis]
        assert {f.primary_metric for f in xgboost} == {"val_log_loss"}
        assert {f.grade_basis for f in xgboost} == {"improvement"}


class TestTheBasisIsStored:
    def test_it_survives_the_database(self, tmp_path: Path) -> None:
        db = str(tmp_path / "runs.db")
        store = RunStore(db_path=db)
        log = LOGS / "xgboost_real_classifier.log"
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("r", str(log)), run_id="r", store=store, hub=Hub()
            )
        )
        again = RunStore(db_path=db).get_story_frames("r")
        assert again[-1].grade_basis == "improvement"

    def test_a_database_from_before_the_column_still_opens(self, tmp_path: Path) -> None:
        """A run stored by an older epochix has no basis: None, not a guess."""
        db = tmp_path / "runs.db"
        store = RunStore(db_path=str(db))
        log = REPO / "demo" / "keras_image_classifier.log"
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("r", str(log)), run_id="r", store=store, hub=Hub()
            )
        )
        del store
        raw = sqlite3.connect(db)
        try:
            raw.execute("ALTER TABLE story_frames DROP COLUMN grade_basis")
            raw.commit()
            columns = [row[1] for row in raw.execute("PRAGMA table_info(story_frames)")]
        finally:
            raw.close()
        assert "grade_basis" not in columns, "premise: the column was removed"

        frames = RunStore(db_path=str(db)).get_story_frames("r")
        assert len(frames) == 20
        assert {f.grade_basis for f in frames} == {None}


class TestTheReportSaysIt:
    def _report(self, log: Path, locale: str) -> str:
        store = RunStore(":memory:")
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("r", str(log)),
                run_id="r",
                store=store,
                hub=Hub(),
                locale=locale,
            )
        )
        return build_markdown(run_id="r", store=store)

    @pytest.mark.parametrize("locale", ["en", "fa", "fr"])
    def test_a_run_graded_on_thresholds(self, locale: str) -> None:
        md = self._report(REPO / "demo" / "keras_image_classifier.log", locale)
        assert t("md.grade_basis", locale) in md
        assert t("grade_basis.thresholds", locale) in md
        assert t("grade_basis.improvement", locale) not in md

    @pytest.mark.parametrize("locale", ["en", "fa", "fr"])
    def test_a_run_graded_on_improvement(self, locale: str) -> None:
        md = self._report(LOGS / "xgboost_real_classifier.log", locale)
        assert t("grade_basis.improvement", locale) in md
        assert t("grade_basis.thresholds", locale) not in md

    def test_every_language_has_its_own_words(self) -> None:
        for key in ("md.grade_basis", "grade_basis.thresholds", "grade_basis.improvement"):
            assert len({t(key, locale) for locale in ("en", "fa", "fr")}) == 3, key
