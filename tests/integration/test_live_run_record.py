"""A live run's record says what the run is while it is still running.

A run is created before its task, parser or story metric is known, holding
placeholders: `val_loss` and parser `unknown`. Only the end-of-stream step
corrected them, and a live run has no end (AGENTS.md: "Streaming has no end").
Driving real runs through `epochix --live` showed it: a Keras run told on
validation accuracy kept a record saying `val_loss` for as long as it ran, and
the dashboard's learning curve, which read the record, drew its accuracy as an
inverted "val loss" curve; the run list called it CUSTOM.

The ingester here behaves like `tail -F`: it yields a real recording's lines,
then never returns, so nothing can come from the end-of-stream code.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

import epochix.pipeline as pipeline
from epochix.enums import TaskType
from epochix.models import RawLogLine
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

LOGS = Path(__file__).resolve().parents[1] / "fixtures" / "logs"


class _TailIngester:
    def __init__(self, path: Path) -> None:
        # Split as the ingesters do: on newlines only, progress redraws kept.
        self._rows = path.read_bytes().decode("utf-8").split("\n")
        self.yielded = 0

    async def lines(self) -> AsyncIterator[RawLogLine]:
        for i, text in enumerate(self._rows, start=1):
            self.yielded = i
            yield RawLogLine(
                seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="stdin"
            )
        while True:
            await asyncio.sleep(3600)


async def _live(log: str, frames_expected: int, monkeypatch: pytest.MonkeyPatch) -> RunStore:
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", 0.02)
    store = RunStore(":memory:")
    ing = _TailIngester(LOGS / log)
    task = asyncio.ensure_future(
        pipeline.run_pipeline(ingester=ing, run_id="live", store=store, hub=Hub())
    )
    try:
        for _ in range(250):  # up to ~5 s
            await asyncio.sleep(0.02)
            if ing.yielded == len(ing._rows) and (
                len(store.get_story_frames("live")) >= frames_expected
            ):
                break
        assert not task.done(), "the stream ended, so this proves nothing"
        return store
    finally:
        task.cancel()


@pytest.mark.parametrize(
    ("log", "frames", "metric", "parser", "task"),
    [
        (
            "keras_real_verbose2.log",
            20,
            "val_accuracy",
            "keras_tensorflow",
            TaskType.CLASSIFICATION,
        ),
        ("catboost_real_classifier.log", 60, "val_score", "boosting", TaskType.CUSTOM),
    ],
)
async def test_the_record_names_the_story_metric_while_the_run_is_live(
    log: str,
    frames: int,
    metric: str,
    parser: str,
    task: TaskType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = await _live(log, frames, monkeypatch)
    told = store.get_story_frames("live")
    assert len(told) == frames
    assert {f.primary_metric for f in told} == {metric}
    run = store.get_run("live")
    assert run is not None
    assert run.finished_at is None, "the run must still be live"
    assert (run.primary_metric, run.parser_used, run.task_type) == (metric, parser, task)


async def test_a_metric_that_never_moves_is_still_told_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CatBoost's AUC is 1.0 every round, so its running best never says which
    way the metric runs and the parser holds the rows. With no end of stream
    to release them, the ten-round limit must: every round is told while the
    run is live, under a name that claims no direction."""
    text = (LOGS / "catboost_real_flat_auc.log").read_text(encoding="utf-8")
    assert text.count("test: 1.0000000") == 30, "the fixture is no longer flat"
    store = await _live("catboost_real_flat_auc.log", 30, monkeypatch)
    told = store.get_story_frames("live")
    assert [f.epoch for f in told] == [float(r) for r in range(30)]
    assert {f.primary_metric for f in told} == {"val_metric"}
    run = store.get_run("live")
    assert run is not None and run.finished_at is None
    assert run.primary_metric == "val_metric"
