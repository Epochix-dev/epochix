"""A metric's name is spoken in the story's own language.

`_display_metric` turned `val_MAE` into "validation MAE" in every locale, so a
French story read "L'erreur validation MAE descend" and a Farsi one carried an
English word mid-sentence. French and Farsi also put the split word after the
metric, which a prefix swap cannot express.
"""

from __future__ import annotations

import re

import pytest

from epochix.story_engine.narrator import (
    _display_metric,
    narrate_diverged,
    narrate_single_reading,
)

PERSIAN = re.compile("[؀-ۿ]")


@pytest.mark.parametrize(
    ("locale", "metric", "spoken"),
    [
        ("en", "val_MAE", "validation MAE"),
        ("en", "train_loss", "training loss"),
        ("fr", "val_MAE", "MAE de validation"),
        ("fr", "train_loss", "loss d'entraînement"),
        ("en", "val_log_loss", "validation log loss"),
        ("fr", "R2", "R2"),
        ("en", None, "error"),
    ],
)
def test_split_words_follow_the_language(locale: str, metric: str | None, spoken: str) -> None:
    assert _display_metric(metric, locale) == spoken


def test_farsi_names_the_split_in_farsi() -> None:
    for metric in ("val_MAE", "train_loss"):
        spoken = _display_metric(metric, "fa")
        assert PERSIAN.search(spoken), spoken
        assert "validation" not in spoken and "training" not in spoken


def test_an_unknown_locale_speaks_english() -> None:
    assert _display_metric("val_MAE", "xx") == "validation MAE"


@pytest.mark.parametrize("run_id", [f"run-{i}" for i in range(12)])
@pytest.mark.parametrize("locale", ["fr", "fa"])
def test_no_english_split_word_reaches_a_translated_story(run_id: str, locale: str) -> None:
    """Across run ids, so every template variant is exercised."""
    stories = [
        narrate_diverged(4, "val_loss", 0.59, 3, run_id, locale),
        narrate_single_reading(0.91, run_id, locale, metric="val_accuracy"),
    ]
    for story in stories:
        # "validation" is French too; what must not appear is the English phrase.
        assert "validation loss" not in story, story
        assert "validation accuracy" not in story, story
        if locale == "fa":
            assert "validation" not in story, story


@pytest.mark.parametrize("run_id", [f"r2-{i}" for i in range(16)])
@pytest.mark.parametrize("locale", ["en", "fr", "fa"])
def test_a_rising_r2_is_never_narrated_as_an_error_falling(run_id: str, locale: str) -> None:
    """R² rises as a model improves; the regression prose is about an error."""
    from epochix.enums import Phase, TaskType
    from epochix.story_engine.narrator import narrate

    for phase in Phase:
        story = narrate(TaskType.REGRESSION, phase, 5, 0.84, 0.06, run_id, locale, metric="val_R2")
        for word in ("error", "erreur", "خطا"):
            assert word not in story.lower(), story
