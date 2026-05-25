"""Ingester unit tests — SDKReceiver, factory."""
from __future__ import annotations

import pytest

from model_story.ingester import make_ingester
from model_story.ingester.sdk_receiver import SDKReceiver


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
        from model_story.ingester.stdin import StdinIngester

        ing = make_ingester(source="stdin", run_id="r1")
        assert isinstance(ing, StdinIngester)

    def test_sdk_ingester(self) -> None:
        ing = make_ingester(source="sdk", run_id="r1")
        assert isinstance(ing, SDKReceiver)

    def test_file_ingester_requires_path(self) -> None:
        with pytest.raises(ValueError, match="path is required"):
            make_ingester(source="file", run_id="r1")

    def test_file_ingester_with_path(self, tmp_path: object) -> None:
        from model_story.ingester.file_tail import FileTailIngester

        ing = make_ingester(source="file", run_id="r1", path="/tmp/test.log")
        assert isinstance(ing, FileTailIngester)

    def test_unknown_source_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown ingester source"):
            make_ingester(source="unknown", run_id="r1")
