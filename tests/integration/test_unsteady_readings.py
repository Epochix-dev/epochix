"""A loss printed per batch is not judged as a loss measured per epoch is.

Every conclusion the engine draws sets one reading against another: the one
before (a spike), the best so far (past its peak), the first (the grade of a
metric with no scale). The recorded LoRA run (`diffusers_lora_real.log`) has
one metric, the loss of the last batch, and on a diffusion model that depends
mostly on which noise level the batch drew. Told as any other loss it was:

* "Past its best … keep the checkpoint from epoch 1 … use early stopping on
  this metric" from its second step;
* a letter that went F, F, A, F, A-, F, F, A … and ended on A by the luck of
  the last batch;
* a divergence warning raised at steps 11, 21, 34 and 73 and withdrawn at 17,
  33 and 70 — standing at the end of a run with nothing wrong.

The readings were right. What was concluded from them was not.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

import pytest

from epochix.exporters.markdown_export import build_markdown
from epochix.i18n import t
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.steadiness import (
    UNSTEADY_MIN_READINGS,
    UNSTEADY_STEP,
    UNSTEADY_TURN_SHARE,
    UNSTEADY_WINDOW,
    Swing,
    swing,
    unsteady,
)
from epochix.story_engine.warnings import _DIVERGE_GROWTH, WarningDetector, standing_warnings

REPO = Path(__file__).resolve().parents[2]
LOGS = REPO / "tests" / "fixtures" / "logs"
LORA = LOGS / "diffusers_lora_real.log"
NANOGPT = LOGS / "nanogpt_real.log"
IMAGENET = LOGS / "pytorch_imagenet_real.log"


def _told(
    log: Path, locale: str = "en"
) -> tuple[RunStore, Run, list[StoryFrame], list[MetricEvent]]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester("u", str(log)),
            run_id="u",
            store=store,
            hub=Hub(),
            locale=locale,
        )
    )
    return store, run, store.get_story_frames("u"), store.get_metric_events("u")


def _series(events: list[MetricEvent], key: str) -> list[float]:
    return [e.value for e in events if e.canonical_key == key]


# ── The measurement ──────────────────────────────────────────────────────────


def test_the_lora_loss_is_the_one_series_that_is_unsteady() -> None:
    """Measured on the recordings, which is where the thresholds come from."""
    lora = _series(_told(LORA)[3], "train_loss")
    found = unsteady(lora)
    assert found is not None
    assert found.readings == UNSTEADY_WINDOW and found.turns == 34
    assert found.step_text == "66%"

    # nanoGPT's loss per iteration turns as often as numbers in no order do,
    # and falls from 4.2 to 1.7 in plain sight: turning is not enough.
    per_iteration = _series(_told(NANOGPT)[3], "train_loss")
    busy = swing(per_iteration)
    assert busy is not None and busy.turns >= UNSTEADY_TURN_SHARE * (busy.readings - 2)
    assert busy.step < 0.05 and unsteady(per_iteration) is None
    assert (per_iteration[0], per_iteration[-1]) == (4.1676, 1.6958)

    # The ImageNet example's loss per batch: the next largest step among
    # training losses that turn half the time, and well short.
    per_batch = _series(_told(IMAGENET)[3], "train_loss")
    close = swing(per_batch)
    assert close is not None and close.turns >= UNSTEADY_TURN_SHARE * (close.readings - 2)
    assert 0.10 < close.step < 0.20 and unsteady(per_batch) is None


def test_a_large_step_alone_is_a_fast_start() -> None:
    halving = [4.0, 2.0, 1.0, 0.5, 0.25, 0.125, 0.0625]
    assert swing(halving) == Swing(readings=7, turns=0, step=0.5)
    assert unsteady(halving) is None


def test_it_takes_both_measures_and_six_readings() -> None:
    zigzag = [0.5, 0.1, 0.4, 0.1, 0.5, 0.1]
    assert len(zigzag) == UNSTEADY_MIN_READINGS
    assert unsteady(zigzag) == Swing(readings=6, turns=4, step=0.8)
    assert unsteady(zigzag[:-1]) is None, "five readings say nothing either way"
    # The step is a share of the larger neighbour, and the bar is inclusive.
    assert UNSTEADY_STEP == 0.25
    assert unsteady([1.0, 0.75, 1.0, 0.75, 1.0, 0.75]) is not None
    assert unsteady([1.0, 0.76, 1.0, 0.76, 1.0, 0.76]) is None


def test_a_run_is_judged_on_how_it_reads_now() -> None:
    """Only the last readings count, so a long steady stretch settles it."""
    noisy = [0.5, 0.1] * 30
    assert unsteady(noisy) is not None
    steady = [0.1 * 0.99**i for i in range(UNSTEADY_WINDOW)]
    assert unsteady(noisy + steady) is None
    assert swing(noisy + steady) == swing(steady)


# ── The LoRA run, through the pipeline ───────────────────────────────────────


def test_the_lora_run_is_not_given_a_letter() -> None:
    _store, run, frames, _events = _told(LORA)
    last = frames[-1]
    assert (last.grade.value, last.grade_basis, last.grade_note) == ("I", None, "unsteady")
    assert run.final_grade is not None and run.final_grade.value == "I"
    # From the sixth reading on; before that there is nothing to tell it by.
    judged = frames[UNSTEADY_MIN_READINGS - 1 :]
    assert len(judged) == 115
    assert {(f.grade.value, f.grade_note) for f in judged} == {("I", "unsteady")}
    # The readings themselves are untouched: charted as logged.
    assert [f.primary_metric_value for f in frames][:3] == [0.00856, 0.0162, 0.025]
    assert last.primary_metric_value == 0.00357


def test_the_lora_run_is_not_told_to_stop_early_or_that_it_is_diverging() -> None:
    _store, _run, frames, _events = _told(LORA)
    judged = frames[UNSTEADY_MIN_READINGS - 1 :]
    for frame in judged:
        assert "early stopping" not in frame.narrative, frame.narrative
        assert "ast its best" not in frame.narrative, frame.narrative
        assert "since the previous reading" not in frame.narrative, frame.narrative
    # Not one divergence warning, at any step — so none to withdraw, either.
    assert Counter(w.kind for f in frames for w in f.warnings) == {}
    assert standing_warnings(w for f in frames for w in f.warnings) == []
    # And it is not walked through the phases on the luck of a batch.
    assert [f.phase.value for f in judged] == ["awakening"] * 6 + ["learning"] * 109


def test_what_is_still_said_before_the_sixth_reading() -> None:
    """Pinned so it is known, not because it is right: with two to five
    readings nothing tells a batch's luck from a real rise, and the sentence
    for a metric that rose is the one for any metric."""
    _store, _run, frames, _events = _told(LORA)
    early = frames[: UNSTEADY_MIN_READINGS - 1]
    assert [f.grade.value for f in early] == ["I", "F", "F", "A", "F"]
    assert ["ast its best" in f.narrative for f in early] == [False, True, True, False, True]


@pytest.mark.parametrize(
    ("locale", "phrases"),
    [
        ("en", ("changed direction 34 times", "the last 50", "differ by 66%", "Next step:")),
        ("fr", ("changé de sens 34 fois", "50 dernières", "de 66%", "Étape suivante")),
        ("fa", ("34 بار تغییر جهت", "50 خوانش اخیر", "66%", "گام بعدی")),
    ],
)
def test_the_story_states_what_was_measured(locale: str, phrases: tuple[str, ...]) -> None:
    _store, _run, frames, _events = _told(LORA, locale)
    last = frames[-1].narrative
    for phrase in phrases:
        assert phrase in last, last
    # The reading and where it was taken, as every sentence carries them.
    assert "0.0036" in last and "120" in last
    # Both variants of the sentence, whichever this run drew, in every frame.
    for frame in frames[UNSTEADY_MIN_READINGS - 1 :]:
        assert f"{frame.primary_metric_value:.4f}" in frame.narrative


def test_the_report_says_why_there_is_no_letter() -> None:
    store, run, _frames, _events = _told(LORA)
    report = build_markdown(run.id, store)
    assert t("grade_note.unsteady", "en") in report
    # "How it was graded" has nothing to say: it was not.
    assert t("md.grade_basis", "en") not in report
    for locale in ("en", "fr", "fa"):
        assert "grade_note.unsteady" not in t("grade_note.unsteady", locale)
    assert store.get_story_frames("u")[-1].grade_note == "unsteady"


def test_the_other_step_counted_runs_are_judged_as_before() -> None:
    for log, grade, basis in ((NANOGPT, "A-", "improvement"), (IMAGENET, "A-", "thresholds")):
        _store, _run, frames, _events = _told(log)
        assert (frames[-1].grade.value, frames[-1].grade_basis) == (grade, basis)
        assert all(f.grade_note != "unsteady" for f in frames)


# ── The detector ─────────────────────────────────────────────────────────────


def _replay(losses: list[float]) -> list[tuple[int, str, str]]:
    det = WarningDetector()
    out: list[tuple[int, str, str]] = []
    for n, loss in enumerate(losses, start=1):
        fired = det.update(n, train_loss=loss, train_swing=unsteady(losses[:n]))
        out += [(n, w.kind, w.message) for w in fired]
    return out


def test_a_tenfold_jump_is_how_an_unsteady_loss_moves() -> None:
    lora = _series(_told(LORA)[3], "train_loss")
    jumps = [b / a for a, b in zip(lora, lora[1:], strict=False) if b > a * _DIVERGE_GROWTH]
    # Two rises of more than tenfold in one reading (12.8 and 17.4 times), and
    # most readings more than ten times the luckiest batch.
    assert len(jumps) == 2, "the recording no longer shows what this is about"
    assert sum(1 for x in lora if x > min(lora) * _DIVERGE_GROWTH) > 20
    assert _replay(lora) == []


def test_a_real_explosion_in_an_unsteady_loss_is_still_reported() -> None:
    noisy = [0.01, 0.004, 0.03, 0.006, 0.02, 0.005, 0.025, 0.007]
    assert unsteady(noisy) is not None
    # Under ten times the highest reading there has been (0.03): one more swing.
    assert _replay([*noisy, 0.29]) == []
    assert _replay([*noisy, 0.31]) == [
        (
            9,
            "divergence",
            "Training loss reached 0.31, more than 10 times the highest reading before "
            "it (0.03). A lower learning rate or gradient clipping may help.",
        )
    ]


def test_a_loss_that_keeps_climbing_stops_being_unsteady_and_is_reported() -> None:
    """Doubling every reading never clears ten times the highest so far. But a
    loss that only rises is not changing direction, and is then judged as any
    loss is: against its best."""
    noisy = [0.01, 0.004, 0.03, 0.006, 0.02, 0.005, 0.025, 0.007]
    climb = [0.03 * 2**n for n in range(1, 12)]
    losses = [*noisy, *climb]
    fired = _replay(losses)
    assert [kind for _n, kind, _m in fired] == ["divergence"]
    at = fired[0][0]
    assert unsteady(losses[: at - 1]) is not None and unsteady(losses[:at]) is None
    assert fired[0][2].startswith(f"Training loss reached {losses[at - 1]:.4g}, more than 10 times")
    assert "its best of 0.004" in fired[0][2]


def test_a_jump_reported_before_the_loss_was_known_to_be_unsteady_is_withdrawn() -> None:
    """Raised on one reading's jump at the fourth reading; by the sixth the
    readings show that is how this loss moves."""
    losses = [0.02, 0.004, 0.001, 0.03, 0.002, 0.02, 0.003]
    assert unsteady(losses[:5]) is None and unsteady(losses[:6]) is not None
    fired = _replay(losses)
    assert [(n, kind) for n, kind, _m in fired] == [(4, "divergence"), (6, "divergence_cleared")]
    assert fired[1][2] == (
        "Training loss changed direction 3 times in its last 6 readings and typically "
        "differs by 90% from one to the next, so one jump does not show that it is diverging."
    )


def test_a_jump_far_above_everything_before_it_is_not_withdrawn() -> None:
    losses = [0.02, 0.004, 0.001, 5.0, 0.002, 0.02, 0.003]
    assert unsteady(losses[:6]) is not None
    assert [(n, kind) for n, kind, _m in _replay(losses)] == [(4, "divergence")]


def test_a_steady_loss_is_warned_exactly_as_before() -> None:
    assert [(n, k) for n, k, _m in _replay([2.0, 1.0, 0.5, 0.05, 0.6, 0.04])] == [
        (5, "divergence"),
        (6, "divergence_cleared"),
    ]
    assert [(n, k) for n, k, _m in _replay([0.5, 500.0, 400.0, 300.0])] == [(2, "divergence")]


def test_every_language_states_the_bar_and_the_measurement() -> None:
    from epochix.story_engine.messages import MESSAGES

    assert f"{_DIVERGE_GROWTH:g}" == "10"
    ten = {"en": "10 times", "fr": "10 fois", "fa": "۱۰ برابر"}
    for locale, phrase in ten.items():
        above = MESSAGES[locale]["warn_above"]
        assert phrase in above and "{new}" in above and "{high}" in above, locale
        withdrawn = MESSAGES[locale]["warn_divergence_unsteady"]
        for field in ("{turns}", "{readings}", "{step}"):
            assert field in withdrawn, (locale, field)
        assert "next_unsteady" in MESSAGES[locale]
