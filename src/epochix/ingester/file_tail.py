from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]

from epochix.ingester import BaseIngester
from epochix.models import RawLogLine

# Flush an un-terminated line once it exceeds this, so a newline-free file can't
# grow the buffer without bound. Far larger than any real log line.
_MAX_PARTIAL = 1_048_576  # 1 MiB


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
                    partial += chunk
                    while "\n" in partial:
                        line, partial = partial.split("\n", 1)
                        yield RawLogLine(
                            seq=seq,
                            timestamp=datetime.now(tz=timezone.utc),
                            source="file",
                            text=line,
                        )
                        seq += 1
                    # A file with no newlines (a binary blob, or one giant JSON
                    # line) would otherwise grow `partial` without bound. Flush
                    # it as a line once it's clearly not a normal log line so
                    # memory stays bounded.
                    if len(partial) > _MAX_PARTIAL:
                        yield RawLogLine(
                            seq=seq,
                            timestamp=datetime.now(tz=timezone.utc),
                            source="file",
                            text=partial,
                        )
                        seq += 1
                        partial = ""
                else:
                    # No new data — sleep and poll again
                    await asyncio.sleep(self._poll_interval)
