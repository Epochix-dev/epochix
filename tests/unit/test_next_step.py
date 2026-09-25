"""A run that went wrong is told what to do next, not only what happened.

The engine detected past-peak, stalled, diverged, overfitting and plateaued
runs and described them — then stopped short of the obvious next sentence.
Some variants carried advice and some did not, so whether a reader got a next
step depended on which variant their run id happened to draw. The step is now
one fixed sentence per state, appended after every variant in every locale.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.story_engine.messages import MESSAGES, message
from epochix.story_engine.narrator import (
    _load_diverged,
    _load_special,
    _load_stalled,
    narrate_diverged,
    narrate_past_peak,
    narrate_stalled,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LOCALES = sorted(MESSAGES)

# The words each locale's next step opens with.
_MARKER = {"en": "Next step:", "fa": "گام بعدی:", "fr": "Étape suivante :"}


def test_every_locale_has_a_marker() -> None:
    assert sorted(_MARKER) == LOCALES


def _every_variant(narrate: Callable[[str], str], n_variants: int) -> list[str]:
    """Narrate under enough run ids to draw every variant at least once."""
    seen: dict[str, None] = {}
    for i in range(400):
        seen[narrate(f"run-{i}")] = None
    outputs = list(seen)
    # Guard: a loop that only ever drew one variant would pass vacuously.
    assert len(outputs) == n_variants, f"drew {len(outputs)} of {n_variants} variants"
    return outputs


@pytest.mark.parametrize("locale", LOCALES)
def test_every_past_peak_variant_ends_with_the_step(locale: str) -> None:
    step = message("next_pastpeak", locale, best_epoch="7")
    variants = _load_special("_pastpeak", locale, "")
    for text in _every_variant(
        lambda rid: narrate_past_peak(10.0, 0.61, 0.79, 7.0, rid, locale), len(variants)
    ):
        assert text.endswith(" " + step), text
        assert text.count(_MARKER[locale]) == 1, text
        assert "{" not in text, text


@pytest.mark.parametrize("locale", LOCALES)
def test_every_stalled_variant_ends_with_the_step(locale: str) -> None:
    step = message("next_stalled", locale)
    for text in _every_variant(
        lambda rid: narrate_stalled(8.0, 0.116, 0.101, 8, rid, locale), len(_load_stalled(locale))
    ):
        assert text.endswith(" " + step), text
        assert text.count(_MARKER[locale]) == 1, text
        assert "{" not in text, text


@pytest.mark.parametrize("locale", LOCALES)
def test_every_diverged_variant_ends_with_the_step(locale: str) -> None:
    step = message("next_diverged", locale, last_epoch="3")
    for text in _every_variant(
        lambda rid: narrate_diverged(4.0, "val_loss", 0.59, 3.0, rid, locale),
        len(_load_diverged(locale)),
    ):
        assert text.endswith(" " + step), text
        assert text.count(_MARKER[locale]) == 1, text
        assert "{" not in text, text


@pytest.mark.parametrize("key", ["warn_overfit", "warn_plateau"])
@pytest.mark.parametrize("locale", LOCALES)
def test_the_warnings_that_stopped_short_now_say_what_to_do(key: str, locale: str) -> None:
    assert _MARKER[locale] in message(key, locale)


def test_the_past_peak_step_names_only_what_it_knows() -> None:
    """Past-peak cannot know the cause, so its step may not claim one."""
    for locale in LOCALES:
        assert "overfit" not in message("next_pastpeak", locale).lower()


# ── End to end: a real log through parse(), in every locale ─────────────────


def _overfit_log() -> list[str]:
    # Train loss keeps falling; validation loss bottoms out at epoch 3 and climbs.
    val = [0.90, 0.70, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    return ["device=cpu epochs=8"] + [
        f"Epoch {e}/8 train_loss={0.9 * 0.8**e:.4f} val_loss={v:.4f}" for e, v in enumerate(val, 1)
    ]


@pytest.mark.parametrize("locale", LOCALES)
def test_an_overfit_run_is_told_what_to_do_next(tmp_path: Path, locale: str) -> None:
    from epochix.store.sqlite_store import RunStore

    log = tmp_path / "run.log"
    log.write_text("\n".join(_overfit_log()) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="t", locale=locale)
    frames = RunStore(db_path=db).get_story_frames(run.id)
    assert frames, "no frames produced"

    last = frames[-1].narrative
    assert last.endswith(message("next_pastpeak", locale, best_epoch="3")), last

    warnings = [w for f in frames for w in f.warnings if w.kind == "overfit"]
    assert warnings, "the overfitting warning did not fire"
    assert _MARKER[locale] in warnings[0].message, warnings[0].message
