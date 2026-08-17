"""A regression grade must not depend on the target's units.

The bands for the regression task are MAE bands: A+ at 0.01, F above 2.5. MAE
carries whatever units the target has, so those numbers only mean anything when
the target is normalised. A real scikit-learn Ridge model — R² 0.9960, an
excellent fit — was graded **F**, purely because its targets ran into the
hundreds.

That is worse than the dataset-blindness the project already discloses. Blind
would be declining to judge; this judged confidently and wrongly.

R² is the one regression metric that carries its own scale: the fraction of
variance explained, 1.0 perfect, below 0 worse than predicting the mean.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epochix.enums import Grade, TaskType
from epochix.models import MetricEvent
from epochix.story_engine import StoryEngine
from epochix.story_engine.grade import compute_grade, has_absolute_scale


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


def _run(pairs: list[tuple[str, float]]) -> Grade:
    """Feed events and return the grade on the last frame.

    Asserts a frame was actually produced. The engine buffers until three
    events have arrived, so a short run yields nothing at all — and a test that
    reads the grade as None then passes every assertion about what it "is not".
    """
    eng = StoryEngine(run_id="r")
    grade: Grade | None = None
    for seq, (key, value) in enumerate(pairs, start=1):
        for frame in eng.process_all(_event(key, value, epoch=float(seq), seq=seq)):
            grade = frame.grade
    assert grade is not None, f"no frame emitted for {pairs}"
    return grade


class TestR2IsGradedOnItsOwnScale:
    def test_an_excellent_fit_is_not_an_F(self) -> None:
        """The exact case from a real Ridge run on make_regression data."""
        assert compute_grade(TaskType.REGRESSION, 0.9960, metric="R2") is Grade.A_PLUS

    @pytest.mark.parametrize(
        ("r2", "expected"),
        [
            (0.99, Grade.A_PLUS),
            (0.91, Grade.A),
            (0.72, Grade.B),
            (0.45, Grade.C),
            (0.15, Grade.D),
            (0.0, Grade.F),
            (-3.0, Grade.F),  # worse than predicting the mean
        ],
    )
    def test_the_scale_runs_the_right_way(self, r2: float, expected: Grade) -> None:
        """Regression is a lower-is-better task, so without metric-aware bands
        R² was scored upside down as well as on the wrong scale."""
        assert compute_grade(TaskType.REGRESSION, r2, metric="R2") is expected

    def test_the_same_value_in_MAE_bands_would_be_F(self) -> None:
        """Guard the guard: the task bands really are the wrong ruler here."""
        assert compute_grade(TaskType.REGRESSION, 0.9960) is not Grade.A_PLUS


class TestUnitBearingErrorsAreNotGradedAbsolutely:
    def test_mae_has_no_absolute_scale(self) -> None:
        assert not has_absolute_scale("MAE")
        assert not has_absolute_scale("val_RMSE")

    def test_r2_does(self) -> None:
        assert has_absolute_scale("R2")
        assert has_absolute_scale("val_R2")

    def test_an_improving_mae_run_is_graded_well(self) -> None:
        """Large-unit targets. Under the old absolute bands every value here is
        above 2.5, so a run that cut its error by 85% still graded F."""
        grade = _run([("MAE", v) for v in (900.0, 600.0, 380.0, 220.0, 140.0)])
        assert grade is not None
        assert grade.value.startswith("A"), grade

    def test_a_worsening_mae_run_is_graded_badly(self) -> None:
        """The other direction, so the test above cannot pass by always saying A."""
        grade = _run([("MAE", v) for v in (140.0, 220.0, 380.0, 600.0, 900.0)])
        assert grade is Grade.F, grade

    def test_gaze_keeps_its_absolute_bands(self) -> None:
        """Not every MAE is unit-less. Gaze MAE is an angle: 0.5 degrees is
        genuinely excellent and 20 genuinely poor, whatever the dataset."""
        assert compute_grade(TaskType.GAZE, 0.4) is Grade.A_PLUS
        assert compute_grade(TaskType.GAZE, 25.0) is Grade.F


class TestOneReadingIsNotAVerdict:
    """A "fit once, score once" script — what an ordinary sklearn file does.

    Several metrics arrive, but each is measured exactly once, so the primary
    metric has no history behind it.
    """

    def test_a_single_unit_bearing_measurement_is_incomplete(self) -> None:
        """One MAE: no scale to place it on and no movement to score it by.
        There is nothing to grade, and the enum has always carried "I" for it.
        """
        assert _run([("MAE", 9.83), ("RMSE", 12.25), ("MSE", 150.1)]) is Grade.INCOMPLETE

    def test_a_single_r2_is_still_graded(self) -> None:
        """R² needs no history — it is absolute on its own."""
        assert _run([("R2", 0.996), ("MAE", 9.83), ("RMSE", 12.25)]) is Grade.A_PLUS

    def test_a_second_reading_restores_a_real_grade(self) -> None:
        grade = _run([("MAE", 900.0), ("RMSE", 1200.0), ("MSE", 9000.0), ("MAE", 140.0)])
        assert grade is not Grade.INCOMPLETE
        assert grade.value.startswith("A"), grade


class TestTheStoryMatchesTheGrade:
    def test_a_strong_single_reading_is_not_called_random(self) -> None:
        """The phase is inferred from how far the metric has MOVED, and one
        reading cannot move, so every run began in AWAKENING. A single fit
        scoring R² 0.996 was narrated "Random predictions define epoch ?"
        directly beneath its A+.
        """
        eng = StoryEngine(run_id="r")
        frames = eng.process_all(_event("R2", 0.996, epoch=1.0, seq=1))
        # Warmup buffers until 3 events; drive it with the same reading.
        for seq in (2, 3):
            frames = eng.process_all(_event("R2", 0.996, epoch=float(seq), seq=seq))

        assert frames
        text = frames[-1].narrative.lower()
        for wrong in ("random", "noise", "uncertain", "nowhere to go"):
            assert wrong not in text, f"a 0.996 R2 model narrated as {wrong!r}: {text}"
