from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, cast

from epochix.ingester import BaseIngester
from epochix.ingester.live_lines import LiveLines
from epochix.models import RawLogLine

if TYPE_CHECKING:
    import io

_CHUNK = 65536


class StdinIngester(BaseIngester):
    """Read lines from stdin asynchronously.

    - **Unix/macOS:** uses :func:`asyncio.get_event_loop().connect_read_pipe`
      with a :class:`asyncio.StreamReader` — zero blocking.
    - **Windows:** falls back to a background :class:`threading.Thread` because
      ``loop.connect_read_pipe()`` is not supported for stdin on Windows.
      What it reads is forwarded to an :class:`asyncio.Queue` in the event loop.

    Both read bytes as they arrive and split them in
    :mod:`epochix.ingester.live_lines`: a line ends at its newline, and a bar
    that runs for the whole training has its finished redraws handed on before
    then. Neither reads by line. ``StreamReader.readline()`` waits for a
    newline a LoRA run does not print for hours, and raises once 64 KiB have
    arrived without one; text-mode ``sys.stdin`` ends a line at every lone
    carriage return, so each redraw of an epoch's progress bar arrived as a
    line of its own and was read as a reading.
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
        held = LiveLines()
        while True:
            data = await reader.read(_CHUNK)
            if not data:
                break
            for line in held.feed(data):
                yield line
        for line in held.end():
            yield line

    async def _win32_lines(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=64)
        loop = asyncio.get_event_loop()
        # read1 returns what has arrived, up to the size asked for; read would
        # wait for the whole 64 KiB or the end of the stream.
        read1 = cast("io.BufferedReader", sys.stdin.buffer).read1

        def _put(item: bytes | None) -> None:
            # Wait for room. A chunk dropped because the queue was full would
            # take the middle of a line with it.
            asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()

        def _reader() -> None:
            try:
                while True:
                    data: bytes = read1(_CHUNK)
                    if not data:
                        break
                    _put(data)
            finally:
                _put(None)

        thread = threading.Thread(target=_reader, daemon=True, name="stdin-reader")
        thread.start()
        held = LiveLines()
        while True:
            item = await queue.get()
            if item is None:
                break
            for line in held.feed(item):
                yield line
        for line in held.end():
            yield line
