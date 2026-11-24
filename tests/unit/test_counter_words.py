"""The story names the counter a run counts by.

A run with no epochs has its own counter in the frame's `epoch` slot — a
boosting round, an iteration, a step — and every sentence called it an epoch:
nanoGPT's step 2000 was told "Epoch 2000: validation loss 1.8857", CatBoost's
round 59 "Epoch 59", and `epochix check` printed "epochs seen 201" for 201
iterations.

The parser that reads the number says what it counts (`count_by`), the frame
carries it (`StoryFrame.counter`), and a sentence names it through a
placeholder filled from a table of whole forms, one per language and kind
(`messages.COUNTER_FORMS`). These tests hold the three together: no template
spells the word itself, no form is missing or unused, and each parser says
what it wrote.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from epochix.models import Counter, MetricEvent
from epochix.parsers.base import COUNTED_BY, ParserContext, counter_after
from epochix.parsers.boosting import BoostingParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.step_bar import StepBarParser
from epochix.parsers.universal import UniversalParser
from epochix.story_engine import StoryEngine
from epochix.story_engine.messages import (
    COUNTER_FORMS,
    COUNTERS,
    MESSAGES,
    counter_words,
    message,
)

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "src" / "epochix" / "story_engine" / "templates"
LOCALES = ("en", "fa", "fr")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
# The word for an epoch, as a template or a message might still spell it.
EPOCH_WORD = {
    "en": re.compile(r"\bepochs?\b", re.I),
    "fr": re.compile(r"[ée]poques?", re.I),
    # Not the plural of "دور" (round), "دورها", which begins with the same letters.
    "fa": re.compile("دوره(?!ا)"),
}
# Not told of a run's counter, so free to say "epoch":
# * the single-reading set is told of a run with one reading and nothing in
#   its epoch slot. It says what such a run lacks ("no best epoch") and what
#   to log to get a story ("a value per epoch");
# * term_fix_print is shown when a terminal printed nothing readable, and
#   says what to print: "one line per epoch", with an example line.
NO_COUNTER = ("_single_reading", "[term_fix_print]")


def _about_a_counter(where: str) -> bool:
    return not any(exempt in where for exempt in NO_COUNTER)


def _locale(path: Path) -> str:
    parts = path.name.split(".")
    return parts[1] if len(parts) == 3 else "en"


def _templates() -> list[tuple[Path, str, str]]:
    """Every template line, with its file and its language."""
    lines = [
        (path, _locale(path), line.strip())
        for path in sorted(TEMPLATES.rglob("*.txt"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) > 350, "the templates went missing"
    return lines


def _sentences() -> list[tuple[str, str, str]]:
    """Every sentence that can name the counter: (where, language, text)."""
    told = [(str(p.relative_to(TEMPLATES)), loc, line) for p, loc, line in _templates()]
    told += [
        (f"messages[{loc}][{key}]", loc, text)
        for loc in LOCALES
        for key, text in MESSAGES[loc].items()
    ]
    return told


def test_the_kinds_are_the_ones_the_table_knows() -> None:
    assert set(COUNTERS) == {"epoch", "step", "iteration", "round"}
    assert set(COUNTER_FORMS) == set(LOCALES)
    for locale, kinds in COUNTER_FORMS.items():
        assert set(kinds) == set(COUNTERS), locale
        for kind, forms in kinds.items():
            # A kind that lacks a form would leave its placeholder in a sentence.
            assert set(forms) == set(kinds["epoch"]), (locale, kind)
            assert all(forms.values()), (locale, kind)


def test_no_sentence_spells_the_counter_itself() -> None:
    """A literal "epoch" in a template is told to a run that has none."""
    offenders = [
        f"{where}: {text}"
        for where, locale, text in _sentences()
        if _about_a_counter(where) and EPOCH_WORD[locale].search(PLACEHOLDER.sub("", text))
    ]
    assert not offenders, "\n".join(offenders)


def test_every_form_is_used_and_every_form_used_is_in_the_table() -> None:
    for locale in LOCALES:
        forms = set(COUNTER_FORMS[locale]["epoch"])
        used = {
            name
            for _where, loc, text in _sentences()
            if loc == locale
            for name in PLACEHOLDER.findall(text)
            if "counter" in name.lower()
        }
        assert used == forms, f"{locale}: unused {forms - used}, missing {used - forms}"


@pytest.mark.parametrize("kind", [k for k in COUNTERS if k != "epoch"])
def test_a_run_without_epochs_is_never_told_of_one(kind: Counter) -> None:
    """Every sentence, in every language, filled for a run that counts by *kind*."""
    checked = 0
    for where, locale, text in _sentences():
        if not _about_a_counter(where):
            continue
        said = counter_words(text, kind, locale)
        assert "counter" not in said.lower(), f"{where}: a placeholder was left in: {said}"
        assert not EPOCH_WORD[locale].search(PLACEHOLDER.sub("", said)), f"{where}: {said}"
        checked += said != text
    assert checked > 300, checked


def test_the_forms_that_count_readings_say_so() -> None:
    """A run told every 250 steps is not read once a step.

    "Over 9 steps" for nine readings 250 steps apart, or "the biggest
    single-step improvement" for the change between two of them, would be
    false; for a run with epochs a reading is an epoch.
    """
    step = lambda key: message(key, "en", "step", value="0.1")  # noqa: E731
    assert step("ms_biggest_jump") == "Biggest single-reading improvement: 0.1"
    assert message("ms_biggest_jump", "en", "epoch", value="0.1") == (
        "Biggest single-epoch improvement: 0.1"
    )
    stalled = (TEMPLATES / "_stalled.txt").read_text(encoding="utf-8").splitlines()[0]
    assert "over {epochs_seen} readings" in counter_words(stalled, "round")
    assert "over {epochs_seen} epochs" in counter_words(stalled, "epoch")
    # ...while a sentence about training further names the counter itself.
    assert "more steps at this rate" in step("warn_plateau")


def test_a_frame_with_no_counter_is_worded_as_an_epoch() -> None:
    """None is an empty epoch slot, or a frame stored before this was recorded."""
    assert counter_words("{Counter} {epoch}", None) == "Epoch {epoch}"
    assert message("next_pastpeak", "fr", best_epoch="7") == message(
        "next_pastpeak", "fr", "epoch", best_epoch="7"
    )
    assert "de l'époque 7" in message("next_pastpeak", "fr", best_epoch="7")


def test_french_agrees_with_a_masculine_counter() -> None:
    """ "à le tour" and "Les tours suivantes" are what a rule would have written."""
    past = (TEMPLATES / "_pastpeak.fr.txt").read_text(encoding="utf-8").splitlines()[1]
    said = counter_words(past, "round", "fr")
    assert "au tour {best_epoch}" in said and "Les tours suivants ne" in said, said
    assert "du tour 6" in message("next_pastpeak", "fr", "round", best_epoch="6")
    assert "au meilleur tour de validation" in message("warn_overfit", "fr", "round")


# ── the parsers say what they put in the epoch slot ──────────────────────────


def _read(parser: object, line: str, ctx: ParserContext, current: Counter = "epoch") -> Counter:
    """The counter after *line*, as the pipeline works it out."""
    slot = ctx.current_epoch
    parser.parse_line(line, ctx)  # type: ignore[attr-defined]
    return counter_after(ctx, slot, current)


@pytest.mark.parametrize(
    ("line", "kind", "at"),
    [
        ("step 250: train loss 2.4293, val loss 2.4447", "step", 250.0),
        ("iter 260: loss 2.4461, time 16.42ms, mfu 0.10%", "iteration", 260.0),
        ("iteration 12 loss 0.52", "iteration", 12.0),
        ("round 7 loss 0.31 accuracy 0.88", "round", 7.0),
        ("Epoch 3/10: loss=0.41 accuracy=0.85", "epoch", 3.0),
    ],
)
def test_a_row_is_counted_by_the_word_it_opens_with(line: str, kind: Counter, at: float) -> None:
    ctx = ParserContext(run_id="t")
    assert _read(UniversalParser(), line, ctx) == kind
    assert ctx.current_epoch == at
    # Said for the line, not kept: the next line speaks for itself.
    assert COUNTED_BY not in ctx.extra


def test_nanogpt_s_step_rows_are_steps_between_its_iter_rows() -> None:
    """Both rows share one slot; each frame is told by the row it came from."""
    parser, ctx = UniversalParser(), ParserContext(run_id="t")
    kinds: list[Counter] = []
    counter: Counter = "epoch"
    for line in (
        "step 0: train loss 4.1676, val loss 4.1649",
        "iter 0: loss 4.1828, time 162.14ms, mfu -100.00%",
        "iter 10: loss 3.7366, time 13.02ms, mfu 0.10%",
        "step 250: train loss 2.4293, val loss 2.4447",
    ):
        counter = _read(parser, line, ctx, counter)
        kinds.append(counter)
    assert kinds == ["step", "iteration", "iteration", "step"]


def test_a_row_that_names_its_epoch_is_counted_by_it() -> None:
    ctx = ParserContext(run_id="t")
    assert _read(UniversalParser(), "step 40: epoch=2 loss=0.5", ctx) == "epoch"
    assert ctx.current_epoch == 2.0


def test_a_boosting_row_is_a_round_and_a_step_bar_a_step() -> None:
    ctx = ParserContext(run_id="t")
    assert _read(BoostingParser(), "[6]\tvalidation_0-logloss:0.17905", ctx) == "round"
    assert ctx.current_epoch == 6.0

    ctx = ParserContext(run_id="t")
    bar = "Steps:  32%|###2      | 39/120 [00:26<00:43,  1.85it/s, loss=0.0129, lr=0.0001]"
    assert _read(StepBarParser(), bar, ctx) == "step"
    assert ctx.current_epoch == 39.0


def test_a_parser_that_says_nothing_wrote_an_epoch() -> None:
    """...and a line that leaves the slot alone leaves the counter alone."""
    ctx = ParserContext(run_id="t")
    assert _read(KerasParser(), "Epoch 4/10", ctx, "round") == "epoch"
    assert ctx.current_epoch == 4.0
    assert _read(KerasParser(), "nothing a parser reads", ctx, "round") == "round"


# ── the frame carries it, and the sentence takes it ──────────────────────────


def _event(seq: int, epoch: float | None, value: float, key: str = "val_loss") -> MetricEvent:
    from datetime import datetime, timezone

    return MetricEvent(
        run_id="c",
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=epoch,
        canonical_key=key,
        raw_key=key,
        value=value,
    )


@pytest.mark.parametrize(
    ("locale", "kind", "said"),
    [
        ("en", "step", "step 3"),
        ("en", "round", "round 3"),
        ("en", "iteration", "iteration 3"),
        ("fr", "step", "étape 3"),
        ("fr", "round", "tour 3"),
        ("fa", "step", "گام 3"),
        ("fa", "round", "دور 3"),
        ("fa", "iteration", "تکرار 3"),
    ],
)
def test_the_engine_tells_a_frame_by_its_counter(locale: str, kind: Counter, said: str) -> None:
    engine = StoryEngine(run_id="c", locale=locale)
    engine.counter = kind
    frames = [
        f
        for seq, v in enumerate((2.0, 1.5, 1.2, 1.0))
        for f in engine.process_all(_event(seq, float(seq), v))
    ]
    assert [f.counter for f in frames] == [kind] * 4
    assert said in frames[-1].narrative.lower(), frames[-1].narrative
    assert not EPOCH_WORD[locale].search(frames[-1].narrative), frames[-1].narrative


def test_a_frame_with_nothing_in_its_slot_counts_by_nothing() -> None:
    """A script that fits once and prints a score has no counter to name."""
    engine = StoryEngine(run_id="c")
    engine.counter = "round"
    engine.process_all(_event(0, None, 0.91, "accuracy"))
    (frame,) = engine.flush_warmup()
    assert frame.epoch is None and frame.counter is None


def test_a_reading_held_through_the_warmup_keeps_the_counter_it_arrived_with() -> None:
    """nanoGPT's first `step` row waits for the `iter` row after it before its
    frame is built; told then by the engine's counter, step 0 was "Iteration 0"."""
    engine = StoryEngine(run_id="c")
    engine.counter = "step"
    assert engine.process_line([_event(0, 0.0, 4.17, "train_loss"), _event(0, 0.0, 4.16)]) == []
    engine.counter = "iteration"
    frames = engine.process_line([_event(1, 0.0, 4.18, "train_loss")])
    assert [(f.primary_metric, f.counter) for f in frames][:1] == [("val_loss", "step")], frames
    assert frames[0].narrative.startswith(("Step 0", "Awakening")), frames[0].narrative
    assert "teration" not in frames[0].narrative
