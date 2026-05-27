from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from epochix.ingester import BaseIngester
from epochix.models import RawLogLine


class StdinIngester(BaseIngester):
    """Read lines from stdin asynchronously.

    - **Unix/macOS:** uses :func:`asyncio.get_event_loop().connect_read_pipe`
      with a :class:`asyncio.StreamReader` — zero blocking.
    - **Windows:** falls back to a background :class:`threading.Thread` because
      ``loop.connect_read_pipe()`` is not supported for stdin on Windows.
      Lines are forwarded to an :class:`asyncio.Queue` in the event loop.
    """

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id

    async def lines(self) -> AsyncIterator[RawLogLine]:
        seq = 0
        reader_fn = self._win32_lines if sys.platform == "win32" else self._unix_lines
        async for text in reader_fn():
            yield RawLogLine(
                seq=seq,
                timestamp=datetime.now(tz=timezone.utc),
                source="stdin",
                text=text,
            )
            seq += 1

    # ------------------------------------------------------------------

    async def _unix_lines(self) -> AsyncIterator[str]:
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        while True:
            raw = await reader.readline()
            if not raw:
                break
            yield raw.decode("utf-8", errors="replace").rstrip("\n")

    async def _win32_lines(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=1024)
        loop = asyncio.get_event_loop()

        def _reader() -> None:
            try:
                for raw_line in sys.stdin:
                    loop.call_soon_threadsafe(queue.put_nowait, raw_line.rstrip("\n"))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = threading.Thread(target=_reader, daemon=True, name="stdin-reader")
        thread.start()
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
