"""A story sentence may say only what the run's numbers support.

The phase stories were written as flavour and filled with real numbers, and
the words around the numbers claimed things no log shows:

* outside standards — "near-expert performance", "competition-grade", "clinical
  precision", "ready to ship", "indistinguishable from real";
* invented specifics — "the model handles glasses, makeup, and partial
  occlusion", "distinguishes car from bicycle, cat from dog", and "the model
  sees faces but not people", told about the bundled FINGERPRINT demo;
* claims that could be false for the run — "the gap between train and val
  narrows", "loss curves bend downward", "only one direction from here".

Now a sentence states the reading, names the phase, and asserts only what the
engine's rules guarantee while a phase story is being told. These tests tie
the words to those rules: change a threshold and the sentences that state it
in words fail here.
"""

from __future__ import annotations

import asyncio
import itertools
import re
from pathlib import Path

import pytest

import epochix.story_engine as engine
from epochix.enums import Phase
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.phases import PHASE_STEPS, compute_phase

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "src" / "epochix" / "story_engine" / "templates"
TASKS = sorted(p.name for p in TEMPLATES.iterdir() if p.is_dir())
PHASES = [p.value for p in Phase]
SCORE_TASKS = {"classification", "detection", "segmentation"}
ERROR_TASKS = {"nlp", "biometric", "generative", "regression", "gaze"}


def _lines(task: str, phase: str, suffix: str = ".txt") -> list[str]:
    path = TEMPLATES / task / f"{phase}{suffix}"
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _all_english() -> list[tuple[str, str, str]]:
    return [(t, p, ln) for t in TASKS for p in PHASES for ln in _lines(t, p)]


def test_the_tasks_are_the_ones_these_tests_know() -> None:
    assert set(TASKS) == SCORE_TASKS | ERROR_TASKS | {"custom"}
    assert len(_all_english()) >= 9 * 5 * 2


# ── words that claim what a log cannot show ──────────────────────────────────

# Outside standards, fitness for use, and specifics about the data or the
# model's behaviour. Bounded and word-anchored; matched case-insensitively.
_UNSUPPORTED_EN = re.compile(
    r"\b("
    r"expert|human|publication|competition|clinical|surgical|photoreal\w{0,8}|indistinguishable|"
    r"deploy\w{0,6}|ship|ready|field|world|exceptional|excellence|optimal|perfect(?!\sscore)|"
    r"robust|reliable|flawless|limit|ceiling|capacity|peak|"
    r"faces?|glasses|makeup|occlusions?|pose|illumination|ageing|iris|bicycle|cat|dog|"
    r"anchors?|boxes|recall|nms|blobs?|textures?|grammar|n-gram|discourse|tokens?|"
    r"memoris\w{0,6}|generalis\w{0,8}|neurons?|gradients?|narrows?|climbs?|falling|rising|steadily"
    r")\b",
    re.I,
)
_UNSUPPORTED_FR = re.compile(
    r"\b(expert\w{0,2}|humain\w{0,2}|clinique|compétition|déploiement|prêt\w{0,2}|"
    r"visages?|lunettes|optimal\w{0,2}|excellence|gradients?|motifs?)\b",
    re.I,
)
# Farsi: expert, human, face, glasses, ready, deployment, gradient.
_UNSUPPORTED_FA = re.compile(r"کارشناس|انسان|چهره|عینک|آماده|استقرار|گرادیان")


def test_no_english_sentence_claims_what_a_log_cannot_show() -> None:
    offenders = [
        f"{task}/{phase}: {line}"
        for task, phase, line in _all_english()
        if _UNSUPPORTED_EN.search(line)
    ]
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize(
    ("suffix", "pattern"), [(".fr.txt", _UNSUPPORTED_FR), (".fa.txt", _UNSUPPORTED_FA)]
)
def test_nor_does_a_translation(suffix: str, pattern: re.Pattern[str]) -> None:
    offenders = [
        f"{task}/{phase}{suffix}: {line}"
        for task in TASKS
        for phase in PHASES
        for line in _lines(task, phase, suffix)
        if pattern.search(line)
    ]
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("suffix", [".txt", ".fr.txt", ".fa.txt"])
def test_every_sentence_carries_its_reading(suffix: str) -> None:
    """The number and the epoch are the story; a sentence without them is flavour."""
    for task in TASKS:
        for phase in PHASES:
            lines = _lines(task, phase, suffix)
            assert len(lines) >= 2, f"{task}/{phase}{suffix} has one variant"
            for line in lines:
                assert "{value" in line, f"{task}/{phase}{suffix}: {line}"
                assert "{epoch}" in line, f"{task}/{phase}{suffix}: {line}"


def test_an_unrecognised_metric_is_only_named() -> None:
    """Its direction is a guess, so no "best so far" and no distance to an ideal."""
    for phase in PHASES:
        for line in _lines("custom", phase):
            assert "{metric}" in line, line
            assert not re.search(r"best|perfect|first reading|\d+%|quarters", line), line


# ── the quantities stated in words ───────────────────────────────────────────


def test_the_thresholds_the_sentences_state_are_the_engine_s() -> None:
    """ "40%", "three quarters", "95%" and "within 1%" are written into the
    templates in three languages. If one of these changes, so must they."""
    bars = {phase: rel for phase, _adv, rel in PHASE_STEPS}
    # A run leaves LEARNING at 40%, UNDERSTANDING at 75%, MASTERING at 95%.
    assert bars == {Phase.LEARNING: 0.40, Phase.UNDERSTANDING: 0.75, Phase.MASTERING: 0.95}
    assert engine._PAST_PEAK_REL_DROP == 0.01


_GRID = [i / 40 for i in range(41)]
_PROGRESS = [None, *_GRID]


def test_a_score_in_mastering_is_three_quarters_of_the_way_to_perfect() -> None:
    """...and in polishing within five points, whatever it started from —
    including the first reading, whose phase is read from the scale itself."""
    seen = {Phase.MASTERING: 0, Phase.POLISHING: 0}
    for baseline, value, progress in itertools.product(_GRID, _GRID, _PROGRESS):
        if value < baseline:
            continue
        phase = compute_phase(progress, value, baseline)
        if phase in (Phase.MASTERING, Phase.POLISHING):
            assert value >= 0.75 - 1e-9, (baseline, value, progress)
            seen[phase] += 1
        if phase is Phase.POLISHING:
            assert value >= 0.95 - 1e-9, (baseline, value, progress)
    assert all(seen.values()), f"the grid never reached a phase: {seen}"


def test_an_error_is_down_by_the_share_its_phase_says() -> None:
    floor = {Phase.UNDERSTANDING: 0.40, Phase.MASTERING: 0.75, Phase.POLISHING: 0.95}
    seen = dict.fromkeys(floor, 0)
    baselines = [0.05, 0.5, 1.0, 7.3, 120.0]
    for baseline, share, progress in itertools.product(baselines, _GRID, _PROGRESS):
        value = baseline * share
        phase = compute_phase(progress, value, baseline, lower_better=True)
        for claimed, cut in floor.items():
            reached = (
                list(floor).index(phase) >= list(floor).index(claimed) if phase in floor else False
            )
            if reached:
                assert value <= baseline * (1 - cut) + 1e-9, (phase, baseline, value, progress)
        if phase in seen:
            seen[phase] += 1
    assert all(seen.values()), f"the grid never reached a phase: {seen}"


@pytest.mark.parametrize("task", sorted(SCORE_TASKS))
def test_score_sentences_state_those_quantities(task: str) -> None:
    assert any("three quarters" in ln for ln in _lines(task, "mastering"))
    assert any(re.search(r"within (five points|0\.05) of", ln) for ln in _lines(task, "polishing"))


@pytest.mark.parametrize("task", sorted(ERROR_TASKS))
def test_error_sentences_state_those_quantities(task: str) -> None:
    assert any("down at least 40%" in ln for ln in _lines(task, "understanding"))
    assert any("down at least three quarters" in ln for ln in _lines(task, "mastering"))
    assert any("down at least 95%" in ln for ln in _lines(task, "polishing"))


# ── the journey ──────────────────────────────────────────────────────────────


def _stories(log: Path) -> list[str]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("s", str(log)), run_id="s", store=store, hub=Hub())
    )
    stories = [f.narrative for f in store.get_story_frames("s")]
    assert stories, f"{log.name} told no story"
    return stories


def test_the_fingerprint_demo_is_not_told_about_faces() -> None:
    """It read "The model sees faces but not people" — on fingerprints."""
    stories = _stories(ROOT / "demo" / "fingerprint_matching.log")
    assert not [s for s in stories if re.search(r"\bfaces?\b", s, re.I)]
    assert all("EER" in s for s in stories), stories


def test_what_the_resnet_run_is_told_is_true_of_it() -> None:
    """Every phase sentence, checked against that frame's own numbers.

    An epoch that dipped more than 1% below the run's best is told by the
    past-peak story instead (its own template, its own tests); those frames
    must be exactly the ones that dipped.
    """
    store = RunStore(":memory:")
    log = ROOT / "tests" / "fixtures" / "logs" / "resnet18_cifar10.log"
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("r", str(log)), run_id="r", store=store, hub=Hub())
    )
    frames = store.get_story_frames("r")
    assert len(frames) == 30
    best = 0.0
    phase_stories = 0
    for frame in frames:
        value = frame.primary_metric_value
        best = max(best, value)
        text = frame.narrative
        dipped = value < best * 0.99
        if dipped:
            assert f"{best:.4f}" in text, f"a dip not told as past its best: {text}"
            continue
        phase_stories += 1
        assert f"{value * 100:.1f}%" in text, text
        if "three quarters" in text or "Most of the distance" in text:
            assert value >= 0.75, text
        assert not _UNSUPPORTED_EN.search(text), text
    # Guard: the checks above must have run on most of the run, not on nothing.
    assert phase_stories >= 20, phase_stories
