"""A reading with none before it is not told how it changed.

Every phase's template set has one variant that quotes the change since the
reading before ("accuracy 20.4%, a change of 0 points since the previous
reading"). A run's first reading, and the first of a metric the story moves
to, has no reading before: it was given a change of 0, and 130 frames of the
corpus (75 of them a run's first) said so in every language. Such a reading
is now told by a variant that states no change, in both engines
(stories.golden.json holds the extension to the same sentences).

Driven through the real pipeline, over every corpus log, in every language
and under run ids that between them pick every variant.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from epochix.enums import Phase, TaskType
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import narrator

REPO = Path(__file__).resolve().parents[2]
TRUTH = json.loads((REPO / "tests" / "fixtures" / "corpus_truth.json").read_text("utf-8"))
GOLDEN = REPO / "epochix-vscode" / "src" / "test" / "fixtures" / "stories.golden.json"
LOCALES = ("en", "fa", "fr")

# What each language's change-quoting variant says after the number.
SINCE_BEFORE = {
    "en": "since the previous reading",
    "fr": "par rapport à la mesure précédente",
    "fa": "نسبت به اندازه‌گیری قبلی",
}


def _told(path: Path, locale: str, run_id: str) -> list[StoryFrame]:
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(
            ingester=FileBatchIngester(run_id, str(path)),
            run_id=run_id,
            store=store,
            hub=Hub(),
            locale=locale,
        )
    )
    return store.get_story_frames(run_id)


def _with_none_before(frames: list[StoryFrame]) -> list[int]:
    """The frames whose story metric had no reading before them.

    A run's first, and the first after the story moves to another metric,
    where the engine restarts what it measures from.
    """
    return [
        i
        for i, frame in enumerate(frames)
        if i == 0 or frames[i - 1].primary_metric != frame.primary_metric
    ]


def _run_ids() -> list[str]:
    ids: list[str] = json.loads(GOLDEN.read_text(encoding="utf-8"))["run_ids"]
    return ids


# ── the templates ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("locale", LOCALES)
def test_every_phase_has_a_variant_that_states_no_change(locale: str) -> None:
    sets = 0
    for task in TaskType:
        for phase in Phase:
            templates = narrator._load_templates(task, phase, locale)
            if any(narrator.states_a_change(t) for t in templates):
                sets += 1
                assert any(not narrator.states_a_change(t) for t in templates), (task, phase)
    assert sets > 20, "no template quotes a change: the rule tests nothing"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_variant_that_states_a_change_says_since_what(locale: str) -> None:
    """The phrase the corpus test looks for is the one every such variant uses."""
    for task in TaskType:
        for phase in Phase:
            for template in narrator._load_templates(task, phase, locale):
                if narrator.states_a_change(template):
                    assert SINCE_BEFORE[locale] in template, (task, phase, template)


def test_a_reading_with_none_before_is_told_without_a_change() -> None:
    for locale in LOCALES:
        for run_id in ("a", "b", "c", "d", "e", "f"):
            said = narrator.narrate(
                TaskType.CLASSIFICATION, Phase.LEARNING, 1, 0.5, None, run_id, locale
            )
            assert SINCE_BEFORE[locale] not in said, said
    # A change of 0 from a reading that was there is still a change of 0.
    told = {
        narrator.narrate(TaskType.CLASSIFICATION, Phase.LEARNING, 2, 0.5, 0.0, f"r{i}")
        for i in range(12)
    }
    assert any("a change of 0 points since the previous reading" in s for s in told), told


# ── the corpus ───────────────────────────────────────────────────────────────


def test_no_reading_with_none_before_states_a_change_anywhere_in_the_corpus() -> None:
    checked = 0
    stated = 0
    for name in sorted(TRUTH):
        path = REPO / TRUTH[name]["path"]
        for locale in LOCALES:
            for run_id in _run_ids():
                frames = _told(path, locale, run_id)
                first = set(_with_none_before(frames))
                for i, frame in enumerate(frames):
                    says = SINCE_BEFORE[locale] in frame.narrative
                    if i in first:
                        checked += 1
                        assert not says, (name, locale, run_id, i, frame.narrative)
                    stated += says
    # Guards: every log in every language and variant was told, and the
    # phrase is one the corpus really says, of readings that have one before.
    assert checked >= len(TRUTH) * len(LOCALES) * len(_run_ids()), checked
    assert stated > 100, stated
