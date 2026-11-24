"""A PSNR or inception-score log, from its text to its frames.

Mirrored by epochix-vscode/src/test/suite/noIdealMetric.test.ts, which feeds
the same lines to the extension's engine and expects the same phases. Each
metric rises the whole run; it used to be placed in Awakening on every frame
and told "No meaningful progress yet".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

PSNR = [20.0, 21.5, 23.0, 24.4, 25.7, 26.9, 28.0, 29.0, 29.9, 30.7, 31.4, 32.0]
IS = [2.0, 2.6, 3.3, 4.0, 4.7, 5.4, 6.0, 6.6, 7.2, 7.8, 8.4, 9.0]

A, L, U, M, P = "awakening", "learning", "understanding", "mastering", "polishing"

# (name in the log, readings, whether the line states the run's length,
#  the story's metric, the phase of each frame, the last letter)
CASES = [
    ("psnr", PSNR, True, "PSNR", [A, L, L, L, L, L, U, U, U, U, U, U], "A"),
    ("psnr", PSNR, False, "PSNR", [A, A, L, L, L, L, U, U, U, U, U, U], "A"),
    ("inception_score", IS, True, "is_score", [A, L, L, L, U, U, U, U, M, M, M, P], "A+"),
    ("inception_score", IS, False, "is_score", [A, L, U, P, P, P, P, P, P, P, P, P], "A+"),
]


def _lines(name: str, values: list[float], with_total: bool) -> list[str]:
    head = "Epoch {}/12 " if with_total else "Epoch {}: "
    return [head.format(i + 1) + f"{name}={v}" for i, v in enumerate(values)]


def _frames(tmp_path: Path, lines: list[str]) -> list[StoryFrame]:
    log = tmp_path / "run.txt"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("n", str(log)), run_id="n", store=store, hub=Hub())
    )
    return store.get_story_frames("n")


@pytest.mark.parametrize(("name", "values", "with_total", "metric", "phases", "grade"), CASES)
def test_a_rising_score_with_no_ideal_moves_through_the_phases(
    tmp_path: Path,
    name: str,
    values: list[float],
    with_total: bool,
    metric: str,
    phases: list[str],
    grade: str,
) -> None:
    frames = _frames(tmp_path, _lines(name, values, with_total))
    assert [f.primary_metric for f in frames] == [metric] * len(values)
    assert [f.primary_metric_value for f in frames] == values
    assert [f.phase.value for f in frames] == phases
    assert frames[-1].grade.value == grade
    assert frames[-1].grade_basis == "improvement"
    for frame in frames:
        assert "progress" not in frame.narrative, frame.narrative
        assert "barely moved" not in frame.narrative, frame.narrative
        assert "where it started" not in frame.narrative, frame.narrative
    if not with_total:
        # No clock: the progress is the rise over the first reading, to 1.
        for frame in frames:
            want = min(1.0, (frame.primary_metric_value - values[0]) / values[0])
            assert frame.progress == pytest.approx(want)
