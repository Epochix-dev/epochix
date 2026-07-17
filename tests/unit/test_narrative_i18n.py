"""Narrative template i18n: completeness and placeholder consistency.

The custom task shipped for months with no fa/fr templates, so a Persian user
got a mirrored RTL dashboard narrating that one task in English. These tests
make a missing or drifted translation a CI failure instead of a silent
English fallback.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).parents[2] / "src" / "epochix" / "story_engine" / "templates"
LOCALES = ("fa", "fr")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _english_templates() -> list[Path]:
    return sorted(
        p
        for p in TEMPLATES.rglob("*.txt")
        if not any(p.name.endswith(f".{loc}.txt") for loc in LOCALES)
    )


def test_there_are_templates_at_all() -> None:
    assert len(_english_templates()) >= 40


@pytest.mark.parametrize("locale", LOCALES)
def test_every_template_is_translated(locale: str) -> None:
    missing = [
        str(en.relative_to(TEMPLATES))
        for en in _english_templates()
        if not en.with_name(f"{en.stem}.{locale}.txt").is_file()
    ]
    assert not missing, f"templates with no {locale} translation: {missing}"


@pytest.mark.parametrize("locale", LOCALES)
def test_translations_use_the_same_placeholders(locale: str) -> None:
    """A translation that drops {value} or invents {foo} breaks narrate()'s
    .format() at runtime — for one locale only, which no English test sees."""
    problems: list[str] = []
    for en in _english_templates():
        tr = en.with_name(f"{en.stem}.{locale}.txt")
        if not tr.is_file():
            continue  # covered by the completeness test
        en_keys = set(_PLACEHOLDER.findall(en.read_text(encoding="utf-8")))
        tr_keys = set(_PLACEHOLDER.findall(tr.read_text(encoding="utf-8")))
        extra = tr_keys - en_keys
        if extra:
            problems.append(f"{tr.relative_to(TEMPLATES)}: unknown placeholders {sorted(extra)}")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("locale", LOCALES)
def test_narrate_renders_the_custom_task_in_locale(locale: str) -> None:
    """End to end through the narrator for the task that was missing."""
    from epochix.enums import Phase, TaskType
    from epochix.story_engine.narrator import narrate

    text = narrate(
        task=TaskType.CUSTOM,
        phase=Phase.LEARNING,
        epoch=3,
        primary_value=0.42,
        delta=0.05,
        run_id="i18n-test",
        locale=locale,
    )
    assert text, "narrate returned nothing"
    if locale == "fa":
        assert re.search(r"[؀-ۿ]", text), f"not Persian: {text!r}"
    else:
        # French templates carry accented characters or the word 'modèle'.
        assert re.search(r"[éèêàôç]|modèle|Époque", text), f"not French: {text!r}"
