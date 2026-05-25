from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from model_story.ingester import BaseIngester
from model_story.models import RawLogLine

_SENTINEL = object()


class SDKReceiver(BaseIngester):
    """In-process asyncio queue fed by :class:`~model_story.sdk.LiveReporter`.

    The LiveReporter calls :meth:`push_line` (thread-safe) from the training
    loop; the ingestion pipeline reads from :meth:`lines`.  Calling
    :meth:`close` inserts a sentinel and ends the iteration.
    """

    def __init__(self, run_id: str, maxsize: int = 4096) -> None:
        self._run_id = run_id
        # Queue holds str lines or the sentinel object.
        self._queue: asyncio.Queue[str | object] = asyncio.Queue(maxsize=maxsize)

    # ------------------------------------------------------------------
    # Producer API (called from training loop, possibly a different thread)
    # ------------------------------------------------------------------

    def push_line(self, text: str) -> None:
        """Put *text* into the queue (non-blocking, thread-safe).

        Lines are silently dropped when the queue is full — metric events
        can tolerate occasional loss; the important signals (grade, milestone)
        are recovered by the story engine from the accumulated history.
        """
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(text)

    def close(self) -> None:
        """Signal end-of-stream so :meth:`lines` stops iterating."""
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(_SENTINEL)

    # ------------------------------------------------------------------
    # Consumer API (async generator)
    # ------------------------------------------------------------------

    async def lines(self) -> AsyncIterator[RawLogLine]:
        seq = 0
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                break
            if isinstance(item, str):
                yield RawLogLine(
                    seq=seq,
                    timestamp=datetime.now(tz=timezone.utc),
                    source="sdk",
                    text=item,
                )
                seq += 1
