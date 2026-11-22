"""Ingester unit tests — SDKReceiver, factory."""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from epochix.ingester import make_ingester
from epochix.ingester.sdk_receiver import SDKReceiver


class TestSDKReceiver:
    @pytest.mark.asyncio
    async def test_push_and_receive_lines(self) -> None:
        rcv = SDKReceiver(run_id="test")
        rcv.push_line("epoch=1 loss=0.5")
        rcv.push_line("epoch=2 loss=0.3")
        rcv.close()

        lines = []
        async for raw in rcv.lines():
            lines.append(raw.text)
        assert lines == ["epoch=1 loss=0.5", "epoch=2 loss=0.3"]

    @pytest.mark.asyncio
    async def test_source_is_sdk(self) -> None:
        rcv = SDKReceiver(run_id="test")
        rcv.push_line("x=1")
        rcv.close()
        async for raw in rcv.lines():
            assert raw.source == "sdk"

    @pytest.mark.asyncio
    async def test_seq_increments(self) -> None:
        rcv = SDKReceiver(run_id="test")
        for i in range(5):
            rcv.push_line(f"val={i}")
        rcv.close()
        seqs = []
        async for raw in rcv.lines():
            seqs.append(raw.seq)
        assert seqs == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_close_without_push_terminates(self) -> None:
        rcv = SDKReceiver(run_id="test")
        rcv.close()
        count = 0
        async for _ in rcv.lines():
            count += 1
        assert count == 0

    def test_push_drops_when_queue_full(self) -> None:
        """push_line must not raise when the queue is at capacity."""
        rcv = SDKReceiver(run_id="test", maxsize=2)
        rcv.push_line("a")
        rcv.push_line("b")
        # Queue is full — this must not raise
        rcv.push_line("c")  # dropped silently


class TestMakeIngester:
    def test_stdin_ingester(self) -> None:
        from epochix.ingester.stdin import StdinIngester

        ing = make_ingester(source="stdin", run_id="r1")
        assert isinstance(ing, StdinIngester)

    def test_sdk_ingester(self) -> None:
        ing = make_ingester(source="sdk", run_id="r1")
        assert isinstance(ing, SDKReceiver)

    def test_file_ingester_requires_path(self) -> None:
        with pytest.raises(ValueError, match="path is required"):
            make_ingester(source="file", run_id="r1")

    def test_file_ingester_with_path(self, tmp_path: object) -> None:
        # "file" = batch mode: read the file once and stop.
        from epochix.ingester.file_batch import FileBatchIngester

        ing = make_ingester(source="file", run_id="r1", path="/tmp/test.log")
        assert isinstance(ing, FileBatchIngester)

    def test_file_tail_ingester_with_path(self) -> None:
        # "file_tail" = live mode: poll the file indefinitely.
        from epochix.ingester.file_tail import FileTailIngester

        ing = make_ingester(source="file_tail", run_id="r1", path="/tmp/test.log")
        assert isinstance(ing, FileTailIngester)

    def test_unknown_source_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown ingester source"):
            make_ingester(source="unknown", run_id="r1")

    async def test_file_tail_flushes_newline_free_content(self, tmp_path: object) -> None:
        """A file with no newline (binary blob / one giant line) must not grow
        the read buffer without bound — it's flushed as a line instead."""
        import asyncio

        from epochix.ingester.file_tail import FileTailIngester
        from epochix.ingester.live_lines import MAX_PARTIAL

        path = tmp_path / "blob.log"  # type: ignore[operator]
        path.write_text("Z" * (MAX_PARTIAL + 4096), encoding="utf-8")  # no "\n"
        ing = FileTailIngester("r1", str(path), poll_interval=0.01)
        gen = ing.lines()
        try:
            line = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            assert len(line.text) >= MAX_PARTIAL  # got the buffered blob, no OOM
        finally:
            await gen.aclose()

    async def test_file_tail_hands_on_a_step_bar_before_its_line_ends(
        self, tmp_path: object
    ) -> None:
        """A LoRA trainer draws one bar for the whole run and ends no line until
        the training does: its finished redraws must not wait for a newline."""
        import asyncio

        from epochix.ingester.file_tail import FileTailIngester
        from epochix.pipeline import _line_states

        cr = chr(13)
        bar = "Steps:   {n}%|#         | {n}/100 [00:26<00:43,  1.85it/s, loss=0.{n}, lr=0.0001]"
        drawn = [bar.format(n=n) for n in (1, 2, 3)]
        path = tmp_path / "lora.log"  # type: ignore[operator]
        path.write_bytes((cr + cr.join(drawn)).encode())  # no newline, as it is on disk
        ing = FileTailIngester("r1", str(path), poll_interval=0.01)
        gen = ing.lines()
        try:
            line = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            # The two finished redraws; the third may still be half written.
            assert _line_states(line.text) == drawn[:2]
            # Its end arrives with the next redraw.
            with path.open("ab") as fh:
                fh.write((cr + bar.format(n=4)).encode())
            line = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            assert _line_states(line.text) == [drawn[2]]
        finally:
            await gen.aclose()

    async def test_file_tail_keeps_an_epoch_bar_until_its_line_ends(self, tmp_path: object) -> None:
        """Every other bar is read in its final state, so it waits for its newline."""
        import asyncio

        from epochix.ingester.file_tail import FileTailIngester

        cr = chr(13)
        path = tmp_path / "epochs.log"  # type: ignore[operator]
        bar = "Epoch 1/12: {n}%|#   | {n}/100 [00:00<00:00, loss=2.3]"
        path.write_bytes((cr + cr.join(bar.format(n=n) for n in (1, 2, 3))).encode())
        ing = FileTailIngester("r1", str(path), poll_interval=0.01)
        gen = ing.lines()
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(gen.__anext__(), timeout=0.3)
        finally:
            await gen.aclose()


# ── A pipe on stdin ──────────────────────────────────────────────────────────
#
# `python train.py 2>&1 | epochix -`. These write to a real pipe standing in
# for stdin and read it through the ingester's own loop: the asyncio pipe
# reader Linux and macOS use, and the reader thread Windows uses (which is
# plain Python and runs anywhere).

_CR = chr(13)
_STEP_BAR = "Steps:   {n}%|#         | {n}/100 [00:26<00:43,  1.85it/s, loss=0.{n}, lr=0.0001]"
_EPOCH_BAR = "Epoch 1/12: {n}%|#   | {n}/100 [00:00<00:00, loss=2.{n}]"
_LOGS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "logs"

_READERS = [
    pytest.param(
        "_unix_lines",
        id="asyncio-pipe",
        marks=pytest.mark.skipif(
            sys.platform == "win32", reason="connect_read_pipe cannot take a pipe on Windows"
        ),
    ),
    pytest.param("_win32_lines", id="reader-thread"),
]


@pytest.fixture
def stdin_pipe(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """Make stdin the read end of a pipe; yield the end to write to."""
    read_fd, write_fd = os.pipe()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(os.fdopen(read_fd, "rb")))
    try:
        yield write_fd
    finally:
        with contextlib.suppress(OSError):
            os.close(write_fd)


async def _all(gen: AsyncIterator[str]) -> list[str]:
    return [text async for text in gen]


async def _to_the_end(gen: AsyncIterator[str], write_fd: int) -> list[str]:
    """Close the pipe and read what is left: the reader must see the end."""
    os.close(write_fd)
    return await asyncio.wait_for(_all(gen), timeout=5.0)


@pytest.mark.parametrize("reader", _READERS)
class TestStdinIngester:
    async def test_hands_on_a_step_bar_before_its_line_ends(
        self, reader: str, stdin_pipe: int
    ) -> None:
        """A LoRA run piped in showed nothing until a checkpoint ended the
        bar's line: readline() was waiting for a newline."""
        from epochix.ingester.stdin import StdinIngester
        from epochix.pipeline import _line_states

        drawn = [_STEP_BAR.format(n=n) for n in (1, 2, 3)]
        os.write(stdin_pipe, (_CR + _CR.join(drawn)).encode())
        gen = getattr(StdinIngester("r1"), reader)()
        text = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
        # The two finished redraws; the third may still be half written.
        assert _line_states(text) == drawn[:2]
        # Its end arrives with the next redraw.
        os.write(stdin_pipe, (_CR + _STEP_BAR.format(n=4)).encode())
        text = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
        assert _line_states(text) == [drawn[2]]
        # And the stream's end finishes the one still being drawn.
        assert await _to_the_end(gen, stdin_pipe) == [_STEP_BAR.format(n=4)]

    async def test_keeps_an_epoch_bar_until_its_line_ends(
        self, reader: str, stdin_pipe: int
    ) -> None:
        """Every other bar is read in its final state. Text-mode stdin ended a
        line at each carriage return on Windows, and every redraw of an epoch's
        bar was a reading."""
        from epochix.ingester.stdin import StdinIngester
        from epochix.pipeline import _line_states

        drawn = [_EPOCH_BAR.format(n=n) for n in (1, 2, 3)]
        os.write(stdin_pipe, (_CR + _CR.join(drawn)).encode())
        gen = getattr(StdinIngester("r1"), reader)()
        first = asyncio.ensure_future(gen.__anext__())
        done, _ = await asyncio.wait({first}, timeout=0.5)
        try:
            assert not done, "a redraw was handed on before the bar's line ended"
            os.write(stdin_pipe, b"\nafter the bar\n")
            assert _line_states(await asyncio.wait_for(first, timeout=5.0)) == [drawn[2]]
            assert await asyncio.wait_for(gen.__anext__(), timeout=5.0) == "after the bar"
        finally:
            assert await _to_the_end(gen, stdin_pipe) == []

    async def test_a_long_bar_line_is_one_line(self, reader: str, stdin_pipe: int) -> None:
        """StreamReader.readline() raised ValueError once 64 KiB had arrived
        with no newline — a minute or two of a tqdm bar."""
        from epochix.ingester.stdin import StdinIngester

        redraws = [_EPOCH_BAR.format(n=n % 100) for n in range(4000)]
        whole = (_CR + _CR.join(redraws) + "\n").encode()
        assert len(whole) > 3 * 65536

        def write() -> None:
            os.write(stdin_pipe, whole)
            os.close(stdin_pipe)

        writer = threading.Thread(target=write)
        writer.start()
        gen = getattr(StdinIngester("r1"), reader)()
        try:
            texts = await asyncio.wait_for(_all(gen), timeout=20.0)
        finally:
            writer.join(timeout=20.0)
        assert len(texts) == 1
        assert texts[0].rsplit(_CR, 1)[-1] == redraws[-1]

    async def test_nothing_is_dropped_when_the_pipe_outruns_the_reader(
        self, reader: str, stdin_pipe: int
    ) -> None:
        """`type train.log | epochix -`: what is read arrives in chunks now, and
        a chunk dropped for want of room would take the middle of a line with
        it. The reader waits for room instead; every line must come through,
        and the stream must still end."""
        from epochix.ingester.stdin import StdinIngester

        sent = [f"epoch={n} loss={1 / (n + 1):.6f}" for n in range(50_000)]
        whole = ("\n".join(sent) + "\n").encode()

        def write() -> None:
            os.write(stdin_pipe, whole)
            os.close(stdin_pipe)

        writer = threading.Thread(target=write)
        writer.start()
        gen = getattr(StdinIngester("r1"), reader)()
        got: list[str] = []

        async def read_slowly() -> None:
            async for text in gen:
                got.append(text)
                if len(got) % 5000 == 0:
                    await asyncio.sleep(0.01)

        try:
            await asyncio.wait_for(read_slowly(), timeout=30.0)
        finally:
            writer.join(timeout=20.0)
        assert got == sent

    @pytest.mark.parametrize("log", ["diffusers_lora_real.log", "tqdm_loop_real.log"])
    async def test_a_piped_run_is_read_as_its_file_is(
        self, reader: str, log: str, stdin_pipe: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole journey: a recorded run through the pipe, the pipeline
        and the store — a bar for the whole run, and a bar per epoch."""
        from epochix.ingester.file_batch import FileBatchIngester
        from epochix.ingester.stdin import StdinIngester
        from epochix.pipeline import run_pipeline
        from epochix.server.hub import Hub
        from epochix.store.sqlite_store import RunStore

        path = _LOGS / log
        recorded = path.read_bytes()
        assert _CR.encode() in recorded

        def write() -> None:
            # In pieces that cut redraws in two, as a pipe does.
            for at in range(0, len(recorded), 1000):
                os.write(stdin_pipe, recorded[at : at + 1000])
            os.close(stdin_pipe)

        async def told(ingester: object, run_id: str) -> list[tuple[str, float | None, float]]:
            store = RunStore(":memory:")
            await run_pipeline(ingester=ingester, run_id=run_id, store=store, hub=Hub())  # type: ignore[arg-type]
            return [(e.canonical_key, e.epoch, e.value) for e in store.get_metric_events(run_id)]

        from_file = await told(FileBatchIngester("f", str(path)), "f")
        assert len(from_file) >= 40

        # lines() picks the reader by platform; ask for the one under test.
        monkeypatch.setattr(sys, "platform", "win32" if reader == "_win32_lines" else "linux")
        writer = threading.Thread(target=write)
        writer.start()
        try:
            from_pipe = await asyncio.wait_for(told(StdinIngester("p"), "p"), timeout=60.0)
        finally:
            writer.join(timeout=20.0)
        assert from_pipe == from_file


# ── What a live source holds, and what it hands on ───────────────────────────


def test_live_lines_completes_a_character_cut_by_a_chunk() -> None:
    from epochix.ingester.live_lines import LiveLines

    bar = "Epoch 1: 50%|█████     | 5/10 [00:01<00:01, loss=0.5]\n".encode()
    cut = bar.index("█".encode()) + 1  # inside the first block character
    held = LiveLines()
    assert held.feed(bar[:cut]) == []
    assert held.feed(bar[cut:]) == [bar.decode().rstrip("\n")]
    assert held.end() == []


def test_live_lines_end_hands_on_the_unfinished_line() -> None:
    from epochix.ingester.live_lines import LiveLines

    held = LiveLines()
    assert held.feed(b"one\ntwo\r\nthr") == ["one", "two\r"]
    assert held.end() == ["thr"]
    assert held.end() == []
