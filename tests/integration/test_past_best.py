"""A run is told it is past its best only once it has stayed there.

The past-best story fired on any reading more than 1% below the best, and it
says more than that: "performance has slipped … the later rounds are moving
away from the best result", then "keep the checkpoint … use early stopping".
A real XGBoost run (`xgboost_real_classifier.log`) converged on a plateau and
wobbled 0.1491, 0.1508, 0.1500: at the middle reading, one round after its
best and 1.1% off it, it was told all of that beside an A+, and the story
switched off again at the next round.

Now a reading that far off is said as just that ("more than 1% off the best
of …"), and the run is told it is past its best, and advised to stop early,
once three readings in a row have been — what early stopping with a patience
of three would do. The sentences state the count, so they claim no more than
was measured.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import epochix.story_engine as engine
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.grade import metric_lower_better
from epochix.story_engine.narrator import _load_special

REPO = Path(__file__).resolve().parents[2]
LOGS = REPO / "tests" / "fixtures" / "logs"
CORPUS = sorted((REPO / "demo").glob("*.log")) + sorted(LOGS.glob("*.log"))

PAST = ("slipped", "Past its best", "below its best")
OFF = "off the best"


def _told(log: Path, locale: str = "en") -> list[StoryFrame]:
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester("p", str(log)),
            run_id="p",
            store=store,
            hub=Hub(),
            locale=locale,
        )
    )
    return store.get_story_frames("p")


def _lines(*accuracies: float) -> list[str]:
    n = len(accuracies)
    return [f"Epoch {e}/{n} val_accuracy={a:.4f}" for e, a in enumerate(accuracies, 1)]


def _told_lines(tmp_path: Path, lines: list[str]) -> list[StoryFrame]:
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return _told(log)


def _past(frame: StoryFrame) -> bool:
    return any(p in frame.narrative for p in PAST)


# ── what is said, reading by reading ─────────────────────────────────────────


def test_one_reading_off_the_best_is_said_as_just_that(tmp_path: Path) -> None:
    frames = _told_lines(tmp_path, _lines(0.60, 0.70, 0.80, 0.78, 0.81))
    off = frames[3]
    assert OFF in off.narrative and "0.8000" in off.narrative and "0.7800" in off.narrative
    assert not _past(off) and "early stopping" not in off.narrative
    # A new best is told as progress again.
    assert OFF not in frames[4].narrative and not _past(frames[4])


def test_three_in_a_row_is_past_its_best(tmp_path: Path) -> None:
    frames = _told_lines(tmp_path, _lines(0.60, 0.70, 0.80, 0.78, 0.77, 0.76, 0.75))
    assert [OFF in f.narrative for f in frames[3:]] == [True, True, False, False]
    assert [_past(f) for f in frames[3:]] == [False, False, True, True]
    assert "early stopping" in frames[-1].narrative
    assert "epoch 3" in frames[-1].narrative and "0.8000" in frames[-1].narrative


def test_a_new_best_starts_the_count_again(tmp_path: Path) -> None:
    frames = _told_lines(tmp_path, _lines(0.60, 0.80, 0.78, 0.77, 0.82, 0.80, 0.79))
    assert not any(_past(f) for f in frames)
    assert [OFF in f.narrative for f in frames] == [False, False, True, True, False, True, True]


def test_within_one_percent_is_neither(tmp_path: Path) -> None:
    frames = _told_lines(tmp_path, _lines(0.60, 0.80, 0.795, 0.793, 0.794, 0.7925))
    assert not any(_past(f) or OFF in f.narrative for f in frames)


def test_a_dip_is_not_called_stalled(tmp_path: Path) -> None:
    """Stalled means flat. A run that went below its best and is not yet told
    so must not be sent after a learning-rate bug instead."""
    frames = _told_lines(tmp_path, _lines(0.80, 0.81, 0.80, 0.80, 0.79, 0.78, 0.79))
    for frame in frames:
        assert "barely moved" not in frame.narrative and "learning rate" not in frame.narrative


# ── the recordings ───────────────────────────────────────────────────────────


def test_a_plateau_s_wobble_is_not_a_slip() -> None:
    frames = _told(LOGS / "xgboost_real_classifier.log")
    assert frames[-1].grade.value == "A+"
    assert not any(_past(f) for f in frames)
    assert not any("early stopping" in f.narrative for f in frames)
    # The two readings more than 1% off the best are still said to be.
    off = [f for f in frames if OFF in f.narrative]
    assert [f.epoch for f in off] == [56.0, 59.0]
    assert "0.1491" in off[-1].narrative and "round 55" in off[-1].narrative


def test_a_run_that_kept_falling_is_still_past_its_best() -> None:
    frames = _told(LOGS / "diverging_loss.log")
    assert _past(frames[-1]) and "early stopping" in frames[-1].narrative


def test_the_corpus_has_dips_and_slips_to_check() -> None:
    """The check below passes on a corpus that never dips. Not this one."""
    told = [_told(log) for log in CORPUS]
    assert sum(1 for frames in told for f in frames if OFF in f.narrative) >= 20
    assert sum(1 for frames in told for f in frames if _past(f)) >= 3
    assert sum(1 for frames in told for f in frames if "within 1%" in f.narrative) >= 20


@pytest.mark.parametrize("log", CORPUS, ids=lambda p: p.name)
def test_no_reading_off_its_best_is_told_as_within_it(log: Path) -> None:
    """The phase stories say a reading is at or within 1% of the best. Over
    every log: a reading further off than that is never told with one, and
    the past-best story is told only after three such readings in a row."""
    frames = _told(log)
    best: float | None = None
    key: str | None = None
    run = 0
    for frame in frames:
        if frame.primary_metric != key:
            key, best, run = frame.primary_metric, None, 0
        lower = metric_lower_better(key or "")
        value = frame.primary_metric_value
        if best is None or (value < best if lower else value > best):
            best = value
        off = abs(best) > 1e-9 and (
            ((value - best) if lower else (best - value)) / abs(best) > engine._PAST_PEAK_REL_DROP
        )
        run = run + 1 if off else 0
        if _past(frame):
            assert run >= engine._PAST_PEAK_READINGS, (frame.epoch, frame.narrative)
        if off and "within 1%" in frame.narrative:
            raise AssertionError(f"{frame.epoch}: {frame.narrative}")


# ── the words state the numbers ──────────────────────────────────────────────

THREE = {"en": "three", "fr": "trois", "fa": "سه"}
ONE_PERCENT = {"en": "1%", "fr": "1 %", "fa": "۱٪"}


@pytest.mark.parametrize("locale", ["en", "fr", "fa"])
def test_every_variant_states_the_count_and_the_drop(locale: str) -> None:
    assert engine._PAST_PEAK_READINGS == 3
    assert engine._PAST_PEAK_REL_DROP == 0.01
    past = _load_special("_pastpeak", locale, "")
    below = _load_special("_belowbest", locale, "")
    assert len(past) >= 3 and len(below) >= 2
    for variant in past:
        assert THREE[locale] in variant and ONE_PERCENT[locale] in variant, variant
    for variant in below:
        assert ONE_PERCENT[locale] in variant, variant
        assert "{best}" in variant and "{best_epoch}" in variant, variant
