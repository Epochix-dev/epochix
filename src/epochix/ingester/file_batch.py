from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]

from epochix.ingester import BaseIngester
from epochix.models import RawLogLine


class FileBatchIngester(BaseIngester):
    """Read a static log file from start to finish, then stop.

    Unlike :class:`~epochix.ingester.file_tail.FileTailIngester` this
    ingester is designed for **batch** processing of already-complete log
    files.  It reads the file once and returns — no polling, no blocking.
    """

    def __init__(
        self,
        run_id: str,
        path: str,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self._run_id = run_id
        self._path = Path(path)
        self._encoding = encoding

    async def lines(self) -> AsyncIterator[RawLogLine]:
        seq = 0
        # newline="\n": split ONLY on newlines. The default (universal newlines)
        # also treats a lone \r as a line break, which shreds progress-bar output
        # — every tqdm/YOLO redraw ("\r 1/3 … 0% … \r 1/3 … 100% …") became its
        # own line and got parsed again, so each epoch's metrics were recorded
        # once per redraw. Keeping the \r inside the line lets _clean_line()
        # collapse it to the final state, which is what the terminal shows.
        async with aiofiles.open(
            self._path, encoding=self._encoding, errors="replace", newline="\n"
        ) as fh:
            async for raw_line in fh:
                text = raw_line.rstrip("\n")
                yield RawLogLine(
                    seq=seq,
                    timestamp=datetime.now(tz=timezone.utc),
                    source="file",
                    text=text,
                )
                seq += 1
