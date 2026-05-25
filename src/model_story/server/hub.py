from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Any, Literal

from model_story.models import WSMessage
from model_story.store.ring_buffer import RingBuffer

_QUEUE_MAXSIZE = 256
_NEVER_DROP: frozenset[str] = frozenset({"milestone", "warning", "complete"})


class Hub:
    """Asyncio broadcast hub — one channel per *run_id*.

    Each subscriber gets its own bounded :class:`asyncio.Queue` (256 items).
    Messages of type ``milestone``, ``warning``, and ``complete`` are **never
    dropped**; older ``story_frame`` messages are evicted first to make room.

    A :class:`~model_story.store.ring_buffer.RingBuffer` per run enables
    replay on reconnect (``?last_seq=N``).

    All public methods are safe to call from the single asyncio event-loop
    thread.  The ring buffer itself is thread-safe.
    """

    def __init__(self) -> None:
        # run_id → set of active subscriber queues
        self._channels: dict[str, set[asyncio.Queue[WSMessage | None]]] = {}
        # run_id → replay buffer
        self._buffers: dict[str, RingBuffer[WSMessage]] = {}

    # ------------------------------------------------------------------
    # Subscription lifecycle
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        run_id: str,
        last_seq: int = -1,
    ) -> asyncio.Queue[WSMessage | None]:
        """Register a subscriber; optionally replay buffered messages.

        Parameters
        ----------
        run_id:
            The run to subscribe to.
        last_seq:
            Last sequence number the client received.  Messages with
            ``seq > last_seq`` are replayed from the ring buffer before
            live events start arriving.  Pass ``-1`` (default) to skip
            replay.

        Returns
        -------
        asyncio.Queue[WSMessage | None]
            Read messages from this queue.  ``None`` signals end-of-stream.
        """
        queue: asyncio.Queue[WSMessage | None] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._channels.setdefault(run_id, set()).add(queue)

        if last_seq >= 0:
            for msg in self._get_buffer(run_id).since(last_seq):
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    break  # queue already near-full; live events will follow

        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[WSMessage | None]) -> None:
        """Remove a subscriber.  Safe to call even if already removed."""
        subs = self._channels.get(run_id)
        if subs is not None:
            subs.discard(queue)
            if not subs:
                del self._channels[run_id]

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, run_id: str, msg: WSMessage) -> None:
        """Fan-out *msg* to every subscriber of *run_id* (non-blocking).

        The message is appended to the run's ring buffer first, so late
        subscribers (reconnects) can replay it.
        """
        self._get_buffer(run_id).append(msg)

        for queue in list(self._channels.get(run_id, ())):
            if queue.full():
                if msg.type in _NEVER_DROP:
                    _coalesce(queue, msg)
                # else: drop silently for slow consumers
            else:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(msg)  # race between full-check and put; drop is safe

    def close_run(self, run_id: str) -> None:
        """Send end-of-stream sentinel (``None``) to all subscribers.

        Called when the training process ends or the run is deleted.
        """
        for queue in list(self._channels.get(run_id, ())):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
        self._channels.pop(run_id, None)

    # ------------------------------------------------------------------
    # Message factory
    # ------------------------------------------------------------------

    @staticmethod
    def make_message(
        *,
        msg_type: Literal["story_frame", "milestone", "warning", "complete", "ping"],
        run_id: str,
        seq: int,
        payload: dict[str, Any],
    ) -> WSMessage:
        """Construct a :class:`~model_story.models.WSMessage` with *now* timestamp."""
        return WSMessage(
            v=1,
            type=msg_type,
            run_id=run_id,
            seq=seq,
            ts=datetime.now(tz=timezone.utc),
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_buffer(self, run_id: str) -> RingBuffer[WSMessage]:
        if run_id not in self._buffers:
            self._buffers[run_id] = RingBuffer(maxlen=2048)
        return self._buffers[run_id]


def _coalesce(
    queue: asyncio.Queue[WSMessage | None],
    important: WSMessage,
) -> None:
    """Evict the oldest droppable message, then enqueue *important*.

    Droppable = type not in ``_NEVER_DROP``.
    This preserves milestone/warning order at the cost of dropping a
    story_frame when the consumer is genuinely too slow.
    """
    items: list[WSMessage | None] = []
    dropped = False
    while not queue.empty():
        try:
            item = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if (
            not dropped
            and item is not None
            and item.type not in _NEVER_DROP
        ):
            dropped = True  # drop this (oldest droppable)
            continue
        items.append(item)
    items.append(important)
    for item in items:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(item)  # extreme edge case — best effort
