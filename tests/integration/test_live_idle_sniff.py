"""Live streaming: frames must appear *before* the stream ends when the
producer pauses between epochs — a run shorter than the sniff window used to
show nothing until finish() (dashboard stuck on 'Waiting for training data')."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest

import epochix.pipeline as pipeline
from epochix.models import RawLogLine
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore


class _SlowIngester:
    """Yields gaze metric lines with a pause between each (mimics real epochs)."""

    def __init__(self, gap: float) -> None:
        self._gap = gap

    async def lines(self) -> AsyncIterator[RawLogLine]:
        rows = [
            "epoch=1 train_loss=15.2 val_loss=52.1 val_mae_cm=9.8",
            "epoch=2 train_loss=13.9 val_loss=50.3 val_mae_cm=9.2",
            "epoch=3 train_loss=12.4 val_loss=49.1 val_mae_cm=8.9",
            "epoch=4 train_loss=11.7 val_loss=48.5 val_mae_cm=8.6",
        ]
        for i, text in enumerate(rows, start=1):
            yield RawLogLine(
                seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="stdin"
            )
            await asyncio.sleep(self._gap)


async def test_frames_emitted_before_stream_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    # Shrink the idle threshold so the test is fast; gap must exceed it.
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", 0.05)

    store = RunStore(":memory:")
    hub = Hub()
    published: list[str] = []
    orig_publish = hub.publish

    def _spy(run_id: str, msg: object) -> None:
        published.append(getattr(msg, "type", "?"))
        orig_publish(run_id, msg)

    monkeypatch.setattr(hub, "publish", _spy)

    await pipeline.run_pipeline(
        ingester=_SlowIngester(gap=0.2),  # 0.2s > 0.05s idle → early sniff fires
        run_id="live",
        store=store,
        hub=hub,
        task=None,
        primary_metric="val_mae_cm",  # raw name — must still resolve (canonicalised)
    )

    frames = store.get_story_frames("live")
    assert len(frames) > 0, "no story frames were produced for a short live run"
    # Frames were broadcast live (not just persisted at the end).
    assert any(t == "story_frame" for t in published)
