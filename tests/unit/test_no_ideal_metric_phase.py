"""A higher-is-better metric with no known ideal is placed by how far it rose.

`relative_improvement` measured every higher-is-better metric against an ideal
of 1.0, the top of an accuracy's scale. PSNR (in decibels) and the inception
score start above 1, so the span to that "ideal" was negative and the
improvement clamped to 0: every frame sat in Awakening and the stall story
fired. A GENERATIVE run whose PSNR climbed 20 -> 32 was told "No meaningful
progress yet ... This usually points to a setup problem", beside an A graded
on that same improvement.

Such a metric has no ideal to measure a share of, so its improvement is taken
from its first reading, as `grade_by_trajectory` takes it, and the stall is
measured the same way. These tests drive the engine line by line, as the
pipeline does.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epochix.enums import Phase
from epochix.models import MetricEvent, StoryFrame
from epochix.story_engine import StoryEngine
from epochix.story_engine.grade import NO_IDEAL_METRICS, has_no_ideal, metric_lower_better
from epochix.story_engine.phases import compute_phase, relative_improvement

_T0 = datetime(2026, 11, 24, tzinfo=timezone.utc)


def _frames(key: str, values: list[float], *, total_epochs: int | None = None) -> list[StoryFrame]:
    """Feed one reading of *key* per epoch, a line each, and collect the frames.
    Either name alone classifies the run GENERATIVE."""
    engine = StoryEngine(run_id="no-ideal", total_epochs=total_epochs)
    frames: list[StoryFrame] = []
    seq = 0
    for epoch, value in enumerate(values, start=1):
        metrics = {key: value}
        events = [
            MetricEvent(
                run_id="no-ideal",
                seq=seq + i,
                timestamp=_T0,
                epoch=float(epoch),
                canonical_key=k,
                raw_key=k,
                value=v,
            )
            for i, (k, v) in enumerate(metrics.items())
        ]
        seq += len(events)
        frames.extend(engine.process_line(events))
    return frames


def _rising(start: float, end: float, n: int) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


_RUNS = [
    ("PSNR", _rising(20.0, 32.0, 12)),
    ("is_score", _rising(2.0, 9.0, 12)),
]


def test_the_metrics_have_no_ideal_and_rise_when_better() -> None:
    """Each is higher-is-better: the measure below assumes a direction."""
    assert {"PSNR", "is_score"} <= NO_IDEAL_METRICS
    for key in NO_IDEAL_METRICS:
        assert metric_lower_better(key) is False, key
        assert has_no_ideal(key)
    # A score on [0, 1] and an error both have an ideal.
    assert not has_no_ideal("accuracy")
    assert not has_no_ideal("val_loss")
    assert not has_no_ideal(None)


@pytest.mark.parametrize(("key", "values"), _RUNS)
@pytest.mark.parametrize("total_epochs", [None, 12])
def test_a_rising_run_is_not_told_it_made_no_progress(
    key: str, values: list[float], total_epochs: int | None
) -> None:
    frames = _frames(key, values, total_epochs=total_epochs)
    assert len(frames) == len(values)
    stories = [f.narrative for f in frames]
    for text in stories:
        assert "No meaningful progress" not in text, text
        assert "barely moved" not in text, text
        assert "where it started" not in text, text
    # It left Awakening, and the last frame is past Learning: PSNR rose 60%
    # of its first reading, the inception score 350%.
    assert frames[-1].phase not in (Phase.AWAKENING, Phase.LEARNING), [f.phase for f in frames]
    # Phases never go back while the metric only rises.
    order = list(Phase)
    seen = [order.index(f.phase) for f in frames]
    assert seen == sorted(seen), [f.phase for f in frames]


@pytest.mark.parametrize(("key", "values"), _RUNS)
def test_without_a_clock_the_progress_is_the_rise_from_the_first_reading(
    key: str, values: list[float]
) -> None:
    frames = _frames(key, values)
    baseline = values[0]
    for frame, value in zip(frames, values, strict=True):
        assert frame.progress == pytest.approx(min(1.0, (value - baseline) / abs(baseline)))


@pytest.mark.parametrize("key", ["PSNR", "is_score"])
def test_a_flat_run_is_still_told_it_stalled(key: str) -> None:
    """The stall is measured from the first reading too: under 3% of it."""
    base = 20.0 if key == "PSNR" else 3.0
    values = [base, base * 1.005, base * 1.01, base * 1.012, base * 1.01]
    frames = _frames(key, values)
    assert any(
        "No meaningful progress" in f.narrative
        or "barely moved" in f.narrative
        or "where it started" in f.narrative
        for f in frames[2:]
    ), [f.narrative for f in frames]
    assert all(f.phase is Phase.AWAKENING for f in frames)


def test_a_run_that_rose_three_percent_is_not_stalled() -> None:
    values = [20.0, 20.3, 20.6, 20.9]
    frames = _frames("PSNR", values)
    assert not any("No meaningful progress" in f.narrative for f in frames)
    assert not any("barely moved" in f.narrative for f in frames)
    assert not any("where it started" in f.narrative for f in frames)


def test_the_measure_is_grade_by_trajectory_s() -> None:
    assert relative_improvement(32.0, 20.0, unbounded=True) == pytest.approx(0.6)
    assert relative_improvement(9.0, 2.0, unbounded=True) == 1.0
    assert relative_improvement(18.0, 20.0, unbounded=True) == 0.0
    # A reward that starts below zero improves by rising towards and past it.
    assert relative_improvement(-200.0, -1500.0, unbounded=True) == pytest.approx(1300 / 1500)
    # Today's answer for a 0-1 score and an error is unchanged.
    assert relative_improvement(0.9, 0.5) == pytest.approx(0.8)
    assert relative_improvement(0.25, 1.0, lower_better=True) == pytest.approx(0.75)
    # And without the flag a score above 1 still reads as no improvement —
    # which is why the engine must pass it.
    assert relative_improvement(32.0, 20.0) == 0.0


def test_with_a_clock_the_phase_still_needs_the_rise() -> None:
    """The clock advances the run; the improvement bars still apply."""
    assert compute_phase(1.0, 32.0, 20.0, unbounded=True) is Phase.UNDERSTANDING
    assert compute_phase(1.0, 40.0, 20.0, unbounded=True) is Phase.POLISHING
    assert compute_phase(1.0, 20.0, 20.0, unbounded=True) is Phase.LEARNING
    assert compute_phase(0.05, 40.0, 20.0, unbounded=True) is Phase.AWAKENING
