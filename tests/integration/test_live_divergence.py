"""A diverged LIVE run must say so while it is still running.

0.7.8 reported a `loss: nan` run as diverged — but only from the end-of-stream
step. A live run has no end (AGENTS.md: "Streaming has no end"), and a diverged
one can keep printing `nan` for hours, so the dashboard showed the grade it had
earned before blowing up until the process finally exited.

The ingester here behaves like `tail -F`: it yields its rows and then never
returns, so the end-of-stream code cannot run. If the divergence frame is in the
store while the stream is still open, it came from the NaN line itself.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest

import epochix.pipeline as pipeline
from epochix.enums import Grade
from epochix.models import RawLogLine
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

ROWS = [
    "Epoch 1/9 - loss: 0.9000 - val_loss: 0.9500",
    "Epoch 2/9 - loss: 0.7000 - val_loss: 0.7600",
    "Epoch 3/9 - loss: 0.5000 - val_loss: 0.5900",
    "Epoch 4/9 - loss: nan - val_loss: nan",
    "Epoch 5/9 - loss: nan - val_loss: nan",
    "Epoch 6/9 - loss: nan - val_loss: nan",
]


class _TailIngester:
    def __init__(self, rows: list[str], *, never_ends: bool) -> None:
        self._rows = rows
        self._never_ends = never_ends
        self.yielded = 0

    async def lines(self) -> AsyncIterator[RawLogLine]:
        for i, text in enumerate(self._rows, start=1):
            self.yielded = i
            yield RawLogLine(
                seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="stdin"
            )
        while self._never_ends:
            await asyncio.sleep(3600)


def _divergence_frames(store: RunStore, run_id: str) -> list:
    return [
        f for f in store.get_story_frames(run_id) if any(w.kind == "divergence" for w in f.warnings)
    ]


async def test_divergence_is_reported_while_the_stream_is_still_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", 0.02)
    store = RunStore(":memory:")
    ing = _TailIngester(ROWS, never_ends=True)
    task = asyncio.ensure_future(
        pipeline.run_pipeline(ingester=ing, run_id="live", store=store, hub=Hub(), task=None)
    )
    try:
        found: list = []
        for _ in range(200):  # up to ~4 s
            await asyncio.sleep(0.02)
            if ing.yielded == len(ROWS):
                found = _divergence_frames(store, "live")
                if found:
                    break
        assert not task.done(), "the stream ended, so this proves nothing"
        assert found, "a live run that went to NaN showed no divergence while running"
        assert found[-1].grade == Grade.F
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_the_divergence_frame_is_published_once() -> None:
    """The end-of-stream call must not add a second copy of the same frame."""
    store = RunStore(":memory:")
    ing = _TailIngester(ROWS, never_ends=False)
    run = await pipeline.run_pipeline(
        ingester=ing, run_id="done", store=store, hub=Hub(), task=None
    )
    assert len(_divergence_frames(store, "done")) == 1
    assert run.final_grade == Grade.F
