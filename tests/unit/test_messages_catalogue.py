"""Warnings and milestones speak the run's language.

They were English literals in the detectors, so a run narrated in Farsi or
French showed English in its warning strip and timeline. Driven through the
real StoryEngine, event by event.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from epochix.models import MetricEvent
from epochix.story_engine import StoryEngine
from epochix.story_engine.messages import MESSAGES, message

PERSIAN = re.compile("[؀-ۿ]")
PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def test_every_locale_has_every_message_with_the_same_placeholders() -> None:
    english = MESSAGES["en"]
    for locale, table in MESSAGES.items():
        assert set(table) == set(english), locale
        for key, text in table.items():
            assert sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(english[key])), (
                locale,
                key,
            )


def test_an_unknown_locale_speaks_english() -> None:
    assert message("ms_complete", "xx") == "Training completed."


def _run(locale: str) -> list[str]:
    """An overfitting run: val loss rising while train loss falls."""
    engine = StoryEngine(run_id="msg", locale=locale)
    seq = 0
    frames = []
    rows = [(1.0, 1.1, 0.3), (0.8, 1.2, 0.55), (0.6, 1.3, 0.7), (0.4, 1.4, 0.8), (0.3, 1.5, 0.86)]
    for epoch, row in enumerate(rows, start=1):
        for key, value in zip(("train_loss", "val_loss", "val_accuracy"), row, strict=True):
            event = MetricEvent(
                run_id="msg",
                seq=seq,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(epoch),
                canonical_key=key,
                raw_key=key,
                value=value,
            )
            seq += 1
            frames.extend(engine.process_all(event))
    texts = [m.message for f in frames for m in f.milestones]
    texts += [w.message for f in frames for w in f.warnings]
    texts += [m.message for m in engine.finalize(seq, 5.0)]
    kinds = {w.kind for f in frames for w in f.warnings}
    assert "overfit" in kinds, "the run did not produce the warning under test"
    assert len(texts) >= 5
    return texts


@pytest.mark.parametrize("locale", ["fa", "fr"])
def test_messages_are_translated(locale: str) -> None:
    english = _run("en")
    translated = _run(locale)
    assert len(translated) == len(english)
    for en, other in zip(english, translated, strict=True):
        assert other != en, f"untranslated under {locale}: {other}"
        assert not PLACEHOLDER.search(other), other
        if locale == "fa":
            assert PERSIAN.search(other), other
