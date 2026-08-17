"""A result is not a stage of training.

The phase templates describe where a run sits in its arc — "the model awakens",
"first patterns emerge from the noise". A script that fits once and prints a
score has no arc: training finished before the first line was printed. Narrating
it as epoch one describes a journey that never happened, and told a finished
98.2% model it was "learning to see".

The distinction has to survive a live run's first epoch, which also has exactly
one reading and IS the beginning of an arc. What separates them is the epoch
axis: every training loop numbers its passes, and a single fit numbers nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from epochix.models import MetricEvent
from epochix.story_engine import StoryEngine

# Words that assert a trajectory. None of them can be true of one measurement.
ARC_WORDS = (
    "awaken",
    "random",
    "noise",
    "emerge",
    "begin",
    "starting",
    "learning to",
    "momentum",
    "epoch ?",
)


def _event(key: str, value: float, seq: int, epoch: float | None) -> MetricEvent:
    return MetricEvent(
        run_id="r",
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=epoch,
        canonical_key=key,
        raw_key=key,
        value=value,
    )


def _drive(events: list[tuple[str, float, float | None]]) -> str:
    """Feed a run and return the last narrative.

    Frames arrive from process_all once the 3-event warmup clears, and from
    flush_warmup when the run ends before it does. Reading only one of the two
    yields an empty list and every assertion about the text passes vacuously.
    """
    eng = StoryEngine(run_id="r")
    frames = []
    for seq, (key, value, epoch) in enumerate(events, start=1):
        frames.extend(eng.process_all(_event(key, value, seq, epoch)))
    frames.extend(eng.flush_warmup())
    assert frames, "the run produced no frame at all"
    return frames[-1].narrative


def _single_fit(key: str, value: float) -> str:
    """A fit-once script: several metrics, each measured once, no epochs."""
    return _drive([(key, value, None), ("f1", 0.981, None), ("precision", 0.977, None)])


class TestASingleFitReadsAsAResult:
    def test_it_does_not_claim_a_trajectory(self) -> None:
        text = _single_fit("val_accuracy", 0.982).lower()
        for word in ARC_WORDS:
            assert word not in text, f"a one-shot result narrated with {word!r}: {text}"

    def test_it_states_the_measurement(self) -> None:
        text = _single_fit("val_accuracy", 0.982)
        assert "0.9820" in text, text

    def test_it_names_the_metric(self) -> None:
        assert "accuracy" in _single_fit("val_accuracy", 0.982).lower()

    def test_it_says_there_is_no_trend(self) -> None:
        text = _single_fit("val_accuracy", 0.982).lower()
        assert any(w in text for w in ("no trend", "no curve", "no trajectory", "once")), text


class TestARealRunKeepsItsStory:
    """The guard that stops the above from flattening every training run.

    Epoch 1 of a live run also has one reading — but it is genuinely the start
    of something, and describing it as a finished result would be its own lie.
    """

    def test_the_first_epoch_of_a_real_run_is_still_a_beginning(self) -> None:
        text = _drive(
            [("val_accuracy", 0.52, 1.0), ("train_loss", 0.69, 1.0), ("f1", 0.50, 1.0)]
        ).lower()
        assert "no trend" not in text and "measured once" not in text, text

    def test_a_multi_epoch_run_is_untouched(self) -> None:
        text = _drive(
            [("val_accuracy", acc, float(i)) for i, acc in enumerate([0.52, 0.61, 0.70, 0.78], 1)]
        ).lower()
        assert "no trend" not in text and "measured once" not in text, text

    @pytest.mark.parametrize("epoch", [0.0, 1.0, 42.0])
    def test_any_numbered_pass_counts_as_an_arc(self, epoch: float) -> None:
        """Boosting rounds start at 0, which must not read as "no epoch"."""
        text = _drive(
            [("val_accuracy", 0.9, epoch), ("f1", 0.88, epoch), ("precision", 0.87, epoch)]
        ).lower()
        assert "measured once" not in text, text
