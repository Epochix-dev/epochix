"""Hub unit tests — backpressure, replay, coalesce."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from model_story.models import WSMessage
from model_story.server.hub import _NEVER_DROP, Hub


def _msg(
    seq: int,
    msg_type: str = "story_frame",
    run_id: str = "r1",
) -> WSMessage:
    return WSMessage(
        v=1,
        type=msg_type,  # type: ignore[arg-type]
        run_id=run_id,
        seq=seq,
        ts=datetime.now(tz=timezone.utc),
        payload={},
    )


class TestHubSubscribeReplay:
    @pytest.mark.asyncio
    async def test_subscribe_receives_published_messages(self) -> None:
        hub = Hub()
        q = await hub.subscribe("r1")
        hub.publish("r1", _msg(1))
        msg = q.get_nowait()
        assert msg is not None
        assert msg.seq == 1

    @pytest.mark.asyncio
    async def test_replay_on_reconnect(self) -> None:
        hub = Hub()
        # Publish before subscribing (buffered)
        hub.publish("r1", _msg(10))
        hub.publish("r1", _msg(11))
        hub.publish("r1", _msg(12))
        # Subscribe with last_seq=10 → should replay seq 11 and 12
        q = await hub.subscribe("r1", last_seq=10)
        msgs = []
        while not q.empty():
            msgs.append(q.get_nowait())
        assert [m.seq for m in msgs if m is not None] == [11, 12]

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self) -> None:
        hub = Hub()
        q = await hub.subscribe("r1")
        hub.unsubscribe("r1", q)
        hub.publish("r1", _msg(1))
        assert q.empty()

    @pytest.mark.asyncio
    async def test_close_run_sends_sentinel(self) -> None:
        hub = Hub()
        q = await hub.subscribe("r1")
        hub.close_run("r1")
        sentinel = q.get_nowait()
        assert sentinel is None


class TestHubBackpressure:
    @pytest.mark.asyncio
    async def test_story_frames_dropped_when_full(self) -> None:
        """story_frame messages are dropped when the queue is full."""
        hub = Hub()
        q = await hub.subscribe("r1")
        # Fill the queue (maxsize=256)
        for i in range(256):
            q.put_nowait(_msg(i))
        assert q.full()
        # Publishing another story_frame should be dropped (not raise)
        hub.publish("r1", _msg(300, msg_type="story_frame"))
        assert q.full()

    @pytest.mark.asyncio
    async def test_milestone_not_dropped_when_full(self) -> None:
        """Milestones must survive even when the queue is at capacity."""
        hub = Hub()
        q = await hub.subscribe("r1")
        # Fill with story_frames (droppable)
        for i in range(256):
            q.put_nowait(_msg(i, msg_type="story_frame"))
        assert q.full()
        important = _msg(999, msg_type="milestone")
        hub.publish("r1", important)
        # Queue should still be full, but contain the milestone
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        milestone_seqs = [m.seq for m in items if m is not None and m.type == "milestone"]
        assert 999 in milestone_seqs

    @pytest.mark.asyncio
    async def test_warning_not_dropped_when_full(self) -> None:
        hub = Hub()
        q = await hub.subscribe("r1")
        for i in range(256):
            q.put_nowait(_msg(i, msg_type="story_frame"))
        hub.publish("r1", _msg(500, msg_type="warning"))
        items = [q.get_nowait() for _ in range(256)]
        warning_seqs = [m.seq for m in items if m is not None and m.type == "warning"]
        assert 500 in warning_seqs


class TestHubMakeMessage:
    def test_make_message_creates_valid_ws_message(self) -> None:
        hub = Hub()
        msg = hub.make_message(
            msg_type="ping",
            run_id="r1",
            seq=0,
            payload={},
        )
        assert msg.type == "ping"
        assert msg.run_id == "r1"
        assert msg.v == 1

    def test_never_drop_set(self) -> None:
        assert "milestone" in _NEVER_DROP
        assert "warning" in _NEVER_DROP
        assert "complete" in _NEVER_DROP
        assert "story_frame" not in _NEVER_DROP
        assert "ping" not in _NEVER_DROP
