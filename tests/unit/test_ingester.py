"""Ingester unit tests — SDKReceiver, factory."""

from __future__ import annotations

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

        from epochix.ingester.file_tail import _MAX_PARTIAL, FileTailIngester

        path = tmp_path / "blob.log"  # type: ignore[operator]
        path.write_text("Z" * (_MAX_PARTIAL + 4096), encoding="utf-8")  # no "\n"
        ing = FileTailIngester("r1", str(path), poll_interval=0.01)
        gen = ing.lines()
        try:
            line = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
            assert len(line.text) >= _MAX_PARTIAL  # got the buffered blob, no OOM
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
