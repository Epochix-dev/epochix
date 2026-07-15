"""The pipeline must close the ingester's async generator deterministically.

Real-SSH testing (an sshd container + `tail -F`) surfaced this: the pipeline
held `ingester.lines().__aiter__()` but never called `aclose()`, so an
ingester's `finally:` block only ran at GC time. For the SSHIngester that meant
the `ssh` subprocess — and the remote `tail -F` — were orphaned on every
interrupted or cancelled run, and released only when Python happened to collect
the generator.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest

import epochix.pipeline as pipeline
from epochix.models import RawLogLine
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore


class _ResourceIngester:
    """Records whether its generator's finally-block ran (i.e. it was closed)."""

    def __init__(self, rows: list[str], *, hang_after: bool) -> None:
        self._rows = rows
        self._hang_after = hang_after
        self.closed = False

    async def lines(self) -> AsyncIterator[RawLogLine]:
        try:
            for i, text in enumerate(self._rows, start=1):
                yield RawLogLine(
                    seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="ssh"
                )
            if self._hang_after:
                # Mimic `tail -F`: never returns on its own. Only aclose() (or a
                # cancel) can end this — exactly the SSH case.
                while True:
                    await asyncio.sleep(3600)
        finally:
            self.closed = True


ROWS = [
    "epoch=1 train_loss=1.8 val_accuracy=0.55",
    "epoch=2 train_loss=1.4 val_accuracy=0.66",
    "epoch=3 train_loss=1.1 val_accuracy=0.74",
]


async def test_generator_closed_when_stream_ends() -> None:
    ing = _ResourceIngester(ROWS, hang_after=False)
    await pipeline.run_pipeline(
        ingester=ing, run_id="done", store=RunStore(":memory:"), hub=Hub(), task=None
    )
    assert ing.closed, "the ingester generator was never closed on normal completion"


async def test_generator_closed_when_run_is_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fast idle ticks so the pipeline is mid-loop (waiting on a never-ending
    # tail) when we cancel it.
    monkeypatch.setattr(pipeline, "IDLE_SNIFF_SECS", 0.02)

    ing = _ResourceIngester(ROWS, hang_after=True)
    task = asyncio.ensure_future(
        pipeline.run_pipeline(
            ingester=ing, run_id="cancel", store=RunStore(":memory:"), hub=Hub(), task=None
        )
    )

    # Let it consume the rows and settle into the tail -F wait.
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert ing.closed, (
        "a cancelled run left the ingester generator open — the SSH subprocess "
        "and remote tail -F would be orphaned"
    )
