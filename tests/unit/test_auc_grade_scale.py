"""An AUC is graded on its own scale, not on how far it moved.

Only accuracy had classification bands, so a run told on its AUC was graded by
improvement from its first reading — and AUC starts high and moves little. A
real LightGBM classifier (tests/fixtures/logs/lightgbm_real_classifier.log)
ended at 0.984 on validation and was graded **C-** for a 2.1% gain from 0.963.

ROC AUC brings its own scale: 0.5 is a coin toss whatever the class balance,
1.0 a perfect ranking. The letters sit on the rule of thumb in Hosmer and
Lemeshow's "Applied Logistic Regression" — 0.7 acceptable, 0.8 excellent, 0.9
outstanding. PR AUC does not get bands: its chance level is the positive
class's share of the data, which no log states. (F1 shares accuracy's bands;
see test_f1_grade_scale.py.)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epochix.enums import Grade, TaskType
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import MetricEvent
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import StoryEngine
from epochix.story_engine.grade import (
    _METRIC_THRESHOLDS,
    compute_grade,
    grade_by_trajectory,
    has_absolute_scale,
    metric_lower_better,
)

REPO = Path(__file__).resolve().parents[2]
LIGHTGBM = REPO / "tests" / "fixtures" / "logs" / "lightgbm_real_classifier.log"


def _event(key: str, value: float, epoch: float, seq: int) -> MetricEvent:
    return MetricEvent(
        run_id="r",
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=epoch,
        canonical_key=key,
        raw_key=key,
        value=value,
    )


def _grades(key: str, values: list[float]) -> list[Grade]:
    """One reading of *key* per epoch; the grade of every frame told on it."""
    engine = StoryEngine(run_id="r")
    grades: list[Grade] = []
    for seq, value in enumerate(values, start=1):
        for frame in engine.process_all(_event(key, value, epoch=float(seq), seq=seq)):
            assert frame.primary_metric == key
            grades.append(frame.grade)
    # Guard: an engine that emitted nothing would pass every "is not" below.
    assert grades, f"no frame emitted for {key} {values}"
    return grades


def _fit_once(pairs: list[tuple[str, float]]) -> list[tuple[str, Grade]]:
    """Several metrics measured once each, with no epoch: a fit-and-score script."""
    engine = StoryEngine(run_id="r")
    told: list[tuple[str, Grade]] = []
    for seq, (key, value) in enumerate(pairs, start=1):
        for frame in engine.process_all(_event(key, value, epoch=1.0, seq=seq)):
            told.append((frame.primary_metric, frame.grade))
    assert told, f"no frame emitted for {pairs}"
    return told


class TestTheScale:
    @pytest.mark.parametrize("metric", ["AUC", "val_AUC"])
    @pytest.mark.parametrize(
        ("auc", "expected"),
        [
            (1.0, Grade.A_PLUS),
            (0.97, Grade.A_PLUS),
            (0.95, Grade.A),
            (0.90, Grade.A_MINUS),  # "outstanding" starts here
            (0.899, Grade.B_PLUS),
            (0.85, Grade.B),
            (0.80, Grade.B_MINUS),  # "excellent"
            (0.799, Grade.C_PLUS),
            (0.75, Grade.C),
            (0.70, Grade.C_MINUS),  # "acceptable"
            (0.699, Grade.D),
            (0.51, Grade.D),
            (0.5, Grade.F),  # a constant prediction: the coin toss, not a pass
            (0.31, Grade.F),  # ranking the classes backwards
        ],
    )
    def test_each_letter_starts_where_the_rule_of_thumb_puts_it(
        self, metric: str, auc: float, expected: Grade
    ) -> None:
        assert compute_grade(TaskType.CLASSIFICATION, auc, metric=metric) is expected

    def test_the_anchors_are_the_published_ones(self) -> None:
        """Change an anchor and this fails: they are quoted, not chosen."""
        bands = dict(_METRIC_THRESHOLDS["val_AUC"])
        assert bands[Grade.A_MINUS] == 0.90
        assert bands[Grade.B_MINUS] == 0.80
        assert bands[Grade.C_MINUS] == 0.70
        assert 0.5 < bands[Grade.D] < 0.5 + 1e-12
        assert _METRIC_THRESHOLDS["AUC"] == _METRIC_THRESHOLDS["val_AUC"]

    def test_higher_is_better_whatever_the_task_says(self) -> None:
        """A metric's bands carry their own direction (as R2's do inside the
        lower-is-better regression task)."""
        assert metric_lower_better("val_AUC") is False
        assert metric_lower_better("AUC") is False
        for task in TaskType:
            assert compute_grade(task, 0.99, metric="val_AUC") is Grade.A_PLUS, task

    def test_the_task_s_accuracy_bands_are_not_what_is_applied(self) -> None:
        """Guard the guard: 0.72 is a B- in accuracy and a C- in AUC."""
        assert compute_grade(TaskType.CLASSIFICATION, 0.72) is Grade.B_MINUS
        assert compute_grade(TaskType.CLASSIFICATION, 0.72, metric="val_AUC") is Grade.C_MINUS


class TestWhichMetricsHaveAScale:
    def test_roc_auc_does(self) -> None:
        assert has_absolute_scale("AUC")
        assert has_absolute_scale("val_AUC")

    @pytest.mark.parametrize("metric", ["PR_AUC", "precision", "recall", "MCC"])
    def test_a_metric_whose_chance_level_depends_on_class_balance_does_not(
        self, metric: str
    ) -> None:
        assert not has_absolute_scale(metric)

    def test_pr_auc_is_still_graded_on_improvement(self) -> None:
        """Same name stem, different metric: its floor is the positive class's
        share, so 0.40 can be excellent or worthless. The engine must not put
        it on the ROC scale."""
        values = [0.40, 0.55, 0.70, 0.80, 0.84]
        assert _grades("PR_AUC", values)[-1] is grade_by_trajectory(0.40, 0.84, False)
        assert compute_grade(TaskType.CLASSIFICATION, 0.84, metric="val_AUC") is not (
            grade_by_trajectory(0.40, 0.84, False)
        ), "the two rules agree here, so this test would not tell them apart"


class TestTheEngineUsesIt:
    def test_the_real_lightgbm_run_is_no_longer_a_c_minus(self) -> None:
        assert LIGHTGBM.stat().st_size > 0
        store = RunStore(":memory:")
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("b", str(LIGHTGBM)), run_id="b", store=store, hub=Hub()
            )
        )
        frames = store.get_story_frames("b")
        assert {f.primary_metric for f in frames} == {"val_AUC"}
        assert frames[-1].primary_metric_value == pytest.approx(0.983648)
        assert frames[-1].grade is Grade.A_PLUS
        # Every frame is graded where its AUC stands, the first included.
        for frame in frames:
            assert frame.grade is compute_grade(
                TaskType.CLASSIFICATION, frame.primary_metric_value, metric="val_AUC"
            ), frame.epoch

    def test_a_barely_moving_auc_is_graded_where_it_stands(self) -> None:
        """The fault itself: 0.963 -> 0.984 is a small move and a strong model."""
        values = [0.963, 0.970, 0.975, 0.980, 0.984]
        assert grade_by_trajectory(values[0], values[-1], False) is Grade.C_MINUS
        assert _grades("val_AUC", values)[-1] is Grade.A_PLUS

    def test_a_large_improvement_does_not_buy_a_good_grade(self) -> None:
        """The other direction, so the test above cannot pass by always saying
        A: 0.52 -> 0.68 is a 31% gain and still short of acceptable."""
        values = [0.52, 0.58, 0.62, 0.66, 0.68]
        assert grade_by_trajectory(values[0], values[-1], False).value.startswith("B")
        assert _grades("val_AUC", values)[-1] is Grade.D

    def test_a_single_auc_is_graded(self) -> None:
        """One reading needs no history when the metric has its own scale — a
        fit-once, score-once script used to get an "I"."""
        pairs = [("val_AUC", 0.91), ("val_log_loss", 0.31), ("val_error_rate", 0.12)]
        assert _fit_once(pairs) == [("val_AUC", Grade.A_MINUS)]
