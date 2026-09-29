"""The README's examples are what Epochix actually says.

The README opened with an example that no version of the engine could produce:
"Mastering phase — Grade B+ … the network has stopped memorising and started
generalising" for epoch 7 of 20, which the engine calls *learning*, in words no
template contains. Its XGBoost example quoted a retired template ("below the
best" of a loss that had got worse), and its SDK snippet printed an attribute
the returned object does not have. For a product whose one rule is that
nothing is invented, the front page was the one place that was.

Each marked example is now run through the real engine: the input is parsed,
and the quoted story must be one of the phrasings the engine chooses between
for exactly those numbers. The SDK snippet is executed as written.
"""

from __future__ import annotations

import contextlib
import io
import re
import shutil
from pathlib import Path

import pytest

from epochix import parse
from epochix.enums import PHASE_EMOJI
from epochix.i18n import t
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.narrator import narrate, narrate_past_peak

REPO = Path(__file__).resolve().parents[2]
README = (REPO / "README.md").read_text(encoding="utf-8")


def _example(name: str) -> str:
    m = re.search(
        rf"<!-- readme-example:{name} -->\n(.*?)<!-- /readme-example:{name} -->", README, re.S
    )
    # Guard: an example that vanished must fail here, not pass by checking nothing.
    assert m, f"README lost its marked {name!r} example"
    return m.group(1)


def _blocks(text: str) -> list[str]:
    return re.findall(r"```[a-z]*\n(.*?)```", text, re.S)


def _frames(tmp_path: Path, log_text: str) -> list:  # type: ignore[type-arg]
    log = tmp_path / "run.log"
    log.write_text(log_text, encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="readme")
    return RunStore(db_path=db).get_story_frames(run.id)


def _phrasings(make: object) -> set[str]:
    """Every sentence the engine would choose between, across run ids."""
    return {make(f"run-{i}") for i in range(400)}  # type: ignore[operator]


def test_the_keras_example_is_the_demo_and_what_it_says(tmp_path: Path) -> None:
    source, output = _blocks(_example("keras"))
    demo = (REPO / "demo" / "keras_image_classifier.log").read_text(encoding="utf-8")
    for line in source.strip().splitlines():
        assert line in demo, f"not a line of the bundled demo: {line!r}"

    frames = _frames(tmp_path, demo)
    last, before = frames[-1], frames[-2]
    heading, story, note = [ln for ln in output.strip().splitlines() if ln.strip()]
    phase = last.phase
    assert heading == (
        f"{PHASE_EMOJI[phase]} {phase.value.title()} phase — Grade {last.grade.value}"
    )
    delta = last.primary_metric_value - before.primary_metric_value
    variants = _phrasings(
        lambda rid: narrate(
            last.task_type,
            phase,
            last.epoch,
            last.primary_metric_value,
            delta,
            rid,
            metric=last.primary_metric,
        )
    )
    assert story in variants, f"{story!r} is not a phrasing the engine uses here"
    assert last.grade_note == "still_improving"
    assert note == t("grade_note.still_improving", "en")


def test_the_xgboost_example_is_what_the_engine_says(tmp_path: Path) -> None:
    text = _example("xgboost")
    (source,) = _blocks(text)
    quote = " ".join(
        ln.lstrip("> ").strip() for ln in text.split("```")[-1].splitlines() if ln.startswith(">")
    ).strip("*")

    frames = _frames(tmp_path, source)
    last = frames[-1]
    series = [f for f in frames if f.primary_metric == last.primary_metric and f.epoch is not None]
    best = min(series, key=lambda f: f.primary_metric_value)  # a log loss: lower is better
    variants = _phrasings(
        lambda rid: narrate_past_peak(
            last.epoch, last.primary_metric_value, best.primary_metric_value, best.epoch, rid
        )
    )
    assert quote in variants, f"{quote!r} is not what the engine says for this log"
    assert last.narrative in variants, "premise: the run did go past its peak"


def test_the_sdk_example_runs_as_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (code,) = _blocks(_example("sdk"))
    shutil.copy(REPO / "demo" / "keras_image_classifier.log", tmp_path / "training.log")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EPOCHIX_DB", str(tmp_path / "runs.db"))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "README.md", "exec"), {})  # noqa: S102 - the README's own snippet
    printed = out.getvalue().strip()
    # What the same log grades as, read independently of the snippet.
    (tmp_path / "check").mkdir()
    last = _frames(tmp_path / "check", (tmp_path / "training.log").read_text(encoding="utf-8"))[-1]
    assert printed.startswith(f"{last.grade.value} "), printed
    assert f"{last.primary_metric_value * 100:.1f}%" in printed, printed
