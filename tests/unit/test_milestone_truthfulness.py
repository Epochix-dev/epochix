"""Milestones must describe what the metric actually did.

`MilestoneTracker` took its direction from the TASK, while the engine grades
and narrates by the METRIC. A custom run graded on `val_loss` and a generative
run graded on FID were both read higher-is-better, so the very first reading —
a loss of 1.2, an FID of 80 — was announced as "Crossed 25%", "50%", "75%" and
"90%" at epoch 1; a loss climbing from 0.5 to 1.3 "crossed 90%" on the way up;
and "Biggest single-epoch improvement" reported the largest step in EITHER
direction, so a run's worst deterioration was celebrated.

These drive the real StoryEngine, event by event, as the pipeline does.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from epochix.models import MetricEvent, Milestone
from epochix.story_engine import StoryEngine


def _drive(
    key: str,
    values: list[float],
    extra: Callable[[int], dict[str, float]] | None = None,
) -> tuple[list[tuple[float | None, Milestone]], list[Milestone]]:
    engine = StoryEngine(run_id=f"ms-{key}")
    seq = 0
    during: list[tuple[float | None, Milestone]] = []
    for epoch, value in enumerate(values, start=1):
        row = {key: value, **(extra(epoch) if extra else {})}
        for k, v in row.items():
            event = MetricEvent(
                run_id=engine.run_id,
                seq=seq,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(epoch),
                canonical_key=k,
                raw_key=k,
                value=v,
            )
            seq += 1
            for frame in engine.process_all(event):
                during.extend((frame.epoch, m) for m in frame.milestones)
    assert during, "no milestones at all — the engine produced no frames"
    return during, engine.finalize(seq, float(len(values)))


def _kinds(during: list[tuple[float | None, Milestone]]) -> set[str]:
    return {m.kind for _, m in during}


def _train(epoch: int) -> dict[str, float]:
    return {"train_loss": 1.3 - epoch * 0.1}


LOSS_LIKE = [
    pytest.param("val_loss", [1.20, 0.90, 0.70, 0.55, 0.50, 0.48], id="falling-val-loss"),
    pytest.param("val_loss", [0.50, 0.60, 0.75, 0.90, 1.10, 1.30], id="rising-val-loss"),
    pytest.param("fid", [80.0, 60.0, 45.0, 38.0, 35.0, 33.0], id="fid"),
    pytest.param("perplexity", [120.0, 80.0, 60.0, 45.0, 40.0, 38.0], id="perplexity"),
]


@pytest.mark.parametrize(("key", "values"), LOSS_LIKE)
def test_no_percentage_milestones_for_a_metric_that_is_not_a_fraction(
    key: str, values: list[float]
) -> None:
    during, _ = _drive(key, values, extra=_train if key == "val_loss" else None)
    crossed = sorted(k for k in _kinds(during) if k.startswith("first_above"))
    assert not crossed, f"{key} {values[:2]}… announced {crossed}"


def test_an_accuracy_logged_as_a_percentage_does_not_cross_thresholds_early() -> None:
    """55.0 on a 0-100 scale is not "above 90%"."""
    during, _ = _drive("val_accuracy", [30.0, 55.0, 70.0, 80.0, 86.0, 91.0], extra=_train)
    assert not [k for k in _kinds(during) if k.startswith("first_above")]


def test_accuracy_crosses_each_threshold_at_the_epoch_it_actually_did() -> None:
    during, _ = _drive("val_accuracy", [0.30, 0.55, 0.70, 0.80, 0.86, 0.91], extra=_train)
    crossed = {m.kind: epoch for epoch, m in during if m.kind.startswith("first_above")}
    assert crossed == {
        "first_above_25": 1.0,
        "first_above_50": 2.0,
        "first_above_75": 4.0,
        "first_above_90": 6.0,
    }


def test_the_biggest_jump_is_an_improvement_not_just_the_biggest_move() -> None:
    # Val loss: largest single move is the 0.50 -> 1.40 blow-up at epoch 4;
    # the largest IMPROVEMENT is 1.20 -> 0.80 at epoch 2.
    _, final = _drive("val_loss", [1.20, 0.80, 0.50, 1.40, 1.30, 1.25], extra=_train)
    jumps = [m for m in final if m.kind == "biggest_jump"]
    assert len(jumps) == 1
    assert jumps[0].value == pytest.approx(0.40)


def test_a_run_that_never_improved_claims_no_biggest_improvement() -> None:
    _, final = _drive("val_loss", [0.50, 0.60, 0.75, 0.90, 1.10, 1.30], extra=_train)
    assert "biggest_jump" not in {m.kind for m in final}


@pytest.mark.parametrize(("key", "values"), LOSS_LIKE)
def test_best_so_far_names_a_value_the_run_really_reached_as_its_best(
    key: str, values: list[float]
) -> None:
    during, _ = _drive(key, values, extra=_train if key == "val_loss" else None)
    best = [m for _, m in during if m.kind == "best_so_far"]
    assert best, "no best_so_far milestone"
    for m in best:
        assert m.value is not None
        # At the moment it fired, nothing earlier in the run was better.
        seen = values[: values.index(m.value) + 1]
        assert m.value == min(seen), f"{key}: 'best' {m.value} was not the lowest of {seen}"
