from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]

from epochix.ingester import BaseIngester
from epochix.ingester.live_lines import take_lines
from epochix.models import RawLogLine


class FileTailIngester(BaseIngester):
    """Tail a file asynchronously, yielding new lines as they appear.

    Uses polling (default 0.1 s) rather than inotify/kqueue because those
    APIs are platform-specific and add complexity for minimal gain at the
    log-file scale.  The 0.1 s interval keeps live latency well under the
    500 ms p95 budget.

    The ingester runs indefinitely; the caller must cancel the coroutine
    (or the enclosing task) to stop it.  If the file grows faster than
    reads, the 64 KB read chunk prevents starvation.
    """

    def __init__(
        self,
        run_id: str,
        path: str,
        *,
        poll_interval: float = 0.1,
        encoding: str = "utf-8",
    ) -> None:
        self._run_id = run_id
        self._path = Path(path)
        self._poll_interval = poll_interval
        self._encoding = encoding

    async def lines(self) -> AsyncIterator[RawLogLine]:
        seq = 0
        partial = ""
        # newline="\n": no universal-newline translation, or a lone \r inside a
        # progress bar is turned into a line break and every tqdm redraw gets
        # parsed as its own epoch row. _clean_line() collapses the \r instead.
        async with aiofiles.open(
            self._path, encoding=self._encoding, errors="replace", newline="\n"
        ) as fh:
            while True:
                chunk: str = await fh.read(65536)
                if chunk:
                    # A line ends at its newline; a bar that runs for the whole
                    # training ends none until the training does, so its
                    # finished redraws go on as they are written (take_lines).
                    lines, partial = take_lines(partial + chunk)
                    for line in lines:
                        yield RawLogLine(
                            seq=seq,
                            timestamp=datetime.now(tz=timezone.utc),
                            source="file",
                            text=line,
                        )
                        seq += 1
                else:
                    # No new data — sleep and poll again
                    await asyncio.sleep(self._poll_interval)
