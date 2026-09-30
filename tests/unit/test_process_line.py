"""StoryEngine.process_line: a frame is built with its whole line recorded.

A frame is built when the story's metric arrives; everything else it reports
is read from history. Fed one event at a time, a metric printed after the
story's metric on the same line belonged to the next frame. Logs that print
`val_acc` before `val_loss` put the overfit check a line behind the losses it
is about.
"""

from __future__ import annotations

from datetime import datetime, timezone

from epochix.models import MetricEvent
from epochix.story_engine import StoryEngine

_T0 = datetime(2026, 9, 30, tzinfo=timezone.utc)

# val_accuracy first, val_loss after it — validation loss rises from epoch 3.
_LINES = [
    (1, {"val_accuracy": 0.60, "val_loss": 0.90, "train_loss": 1.00}),
    (2, {"val_accuracy": 0.70, "val_loss": 0.70, "train_loss": 0.80}),
    (3, {"val_accuracy": 0.72, "val_loss": 0.75, "train_loss": 0.60}),
    (4, {"val_accuracy": 0.71, "val_loss": 0.82, "train_loss": 0.45}),
    (5, {"val_accuracy": 0.70, "val_loss": 0.90, "train_loss": 0.35}),
]


def _events(epoch: int, metrics: dict[str, float], seq: int) -> list[MetricEvent]:
    return [
        MetricEvent(
            run_id="r",
            seq=seq + i,
            timestamp=_T0,
            epoch=float(epoch),
            canonical_key=key,
            raw_key=key,
            value=value,
        )
        for i, (key, value) in enumerate(metrics.items())
    ]


def _overfit_epoch(by_line: bool) -> float | None:
    engine = StoryEngine(run_id="r")
    seq = 0
    for epoch, metrics in _LINES:
        events = _events(epoch, metrics, seq)
        seq += len(events)
        frames = (
            engine.process_line(events)
            if by_line
            else [f for e in events for f in engine.process_all(e)]
        )
        for frame in frames:
            if any(w.kind == "overfit" for w in frame.warnings):
                return frame.epoch
    return None


def test_the_overfit_warning_lands_on_the_epoch_its_losses_are_from() -> None:
    # Validation loss rises across epochs 2 -> 3 -> 4 while training loss falls.
    assert _overfit_epoch(by_line=True) == 4.0


def test_event_by_event_it_was_a_line_late() -> None:
    """The defect, pinned so the comparison above means something."""
    assert _overfit_epoch(by_line=False) == 5.0


def test_one_frame_per_line_either_way() -> None:
    for by_line in (True, False):
        engine = StoryEngine(run_id="r")
        seq, frames = 0, []
        for epoch, metrics in _LINES:
            events = _events(epoch, metrics, seq)
            seq += len(events)
            frames += (
                engine.process_line(events)
                if by_line
                else [f for e in events for f in engine.process_all(e)]
            )
        assert [f.epoch for f in frames] == [1.0, 2.0, 3.0, 4.0, 5.0]
