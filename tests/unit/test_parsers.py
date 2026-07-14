"""Parser unit tests — one per framework fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from epochix.parsers.base import ParserContext
from epochix.parsers.huggingface import HFParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.pytorch_lightning import PLParser
from epochix.parsers.registry import detect_parser
from epochix.parsers.ultralytics_yolo import YOLOParser
from epochix.parsers.universal import UniversalParser

DEMO = Path(__file__).parents[2] / "demo"


def _load_lines(name: str) -> list[str]:
    return (DEMO / name).read_text(encoding="utf-8").splitlines()


# ------------------------------------------------------------------ sniff


class TestPLParserSniff:
    def test_detects_pl_log(self) -> None:
        lines = _load_lines("pytorch_lightning.log")
        assert PLParser().sniff(lines[:50]) > 0.3

    def test_rejects_keras(self) -> None:
        lines = _load_lines("keras_image_classifier.log")
        assert PLParser().sniff(lines[:50]) < 0.3


class TestKerasParserSniff:
    def test_detects_keras_log(self) -> None:
        lines = _load_lines("keras_image_classifier.log")
        assert KerasParser().sniff(lines[:50]) > 0.5

    def test_rejects_hf(self) -> None:
        lines = _load_lines("huggingface_bert.log")
        assert KerasParser().sniff(lines[:50]) < 0.3


class TestHFParserSniff:
    def test_detects_hf_log(self) -> None:
        lines = _load_lines("huggingface_bert.log")
        assert HFParser().sniff(lines[:50]) > 0.5

    def test_rejects_pl(self) -> None:
        lines = _load_lines("pytorch_lightning.log")
        assert HFParser().sniff(lines[:50]) < 0.3


class TestYOLOParserSniff:
    def test_detects_yolo_log(self) -> None:
        lines = _load_lines("yolov8_detection.log")
        assert YOLOParser().sniff(lines[:50]) > 0.3


# ------------------------------------------------------------------ parse


class TestPLParserParse:
    def test_extracts_loss_and_acc(self) -> None:
        line = "Epoch 5/30: 100%|████| 250/250 [00:13<00:00, loss=0.821, acc=0.612]"
        ctx = ParserContext(run_id="test", seq=1)
        metrics = PLParser().parse_line(line, ctx)
        keys = {m.key for m in metrics}
        assert "loss" in keys or "acc" in keys

    def test_epoch_tracked(self) -> None:
        line = "Epoch 5/30: 100%|████| 250/250 [00:13<00:00, loss=0.821, acc=0.612]"
        ctx = ParserContext(run_id="test", seq=1)
        PLParser().parse_line(line, ctx)
        assert ctx.current_epoch == 5.0
        assert ctx.total_epochs == 30

    def test_full_fixture_coverage(self) -> None:
        lines = _load_lines("pytorch_lightning.log")
        parser = PLParser()
        ctx = ParserContext(run_id="test")
        all_metrics = []
        for seq, line in enumerate(lines):
            ctx.seq = seq
            all_metrics.extend(parser.parse_line(line, ctx))
        keys = {m.key for m in all_metrics}
        assert "loss" in keys or "acc" in keys
        assert len(all_metrics) >= 30  # at least one metric per epoch


class TestKerasParserParse:
    def test_extracts_epoch(self) -> None:
        ctx = ParserContext(run_id="test", seq=1)
        KerasParser().parse_line("Epoch 5/20", ctx)
        assert ctx.current_epoch == 5.0

    def test_extracts_metrics(self) -> None:
        line = (
            "1563/1563 [==============================] - 8s - "
            "loss: 1.823 - accuracy: 0.324 - val_loss: 1.654 - val_accuracy: 0.381"
        )
        ctx = ParserContext(run_id="test", seq=1, current_epoch=1.0)
        metrics = KerasParser().parse_line(line, ctx)
        keys = {m.key for m in metrics}
        assert "loss" in keys
        assert "accuracy" in keys


class TestHFParserParse:
    def test_extracts_loss_and_epoch(self) -> None:
        line = "{'loss': 2.3456, 'learning_rate': 5e-05, 'epoch': 1.0}"
        ctx = ParserContext(run_id="test", seq=1)
        metrics = HFParser().parse_line(line, ctx)
        assert any(m.key == "loss" for m in metrics)
        assert ctx.current_epoch == 1.0

    def test_rejects_non_dict_line(self) -> None:
        ctx = ParserContext(run_id="test", seq=1)
        assert HFParser().parse_line("Training started.", ctx) == []


class TestUniversalParser:
    def test_kv_eq(self) -> None:
        line = "loss=0.432 accuracy=0.867"
        ctx = ParserContext(run_id="test", seq=1)
        metrics = UniversalParser().parse_line(line, ctx)
        keys = {m.key for m in metrics}
        assert "loss" in keys
        assert "accuracy" in keys

    def test_kv_colon(self) -> None:
        line = "train_loss: 0.234  val_loss: 0.312"
        ctx = ParserContext(run_id="test", seq=1)
        metrics = UniversalParser().parse_line(line, ctx)
        assert len(metrics) >= 1

    def test_epoch_header_on_metric_line(self) -> None:
        """`Epoch N/M: metrics` (epoch printed on the same line, no key=value
        form) must stamp the metrics with the epoch and set the total, so the
        dashboard shows the epoch number and a progress bar — not "Epoch —"."""
        ctx = ParserContext(run_id="test", seq=1)
        parser = UniversalParser()
        metrics = parser.parse_line("Epoch 1/8: train_loss=2.31 val_accuracy=0.24", ctx)
        assert ctx.current_epoch == 1.0
        assert ctx.total_epochs == 8
        assert all(m.epoch == 1.0 for m in metrics)
        # "Epoch" itself must not become a spurious metric
        assert not any(m.key.lower() == "epoch" for m in metrics)
        # a later line advances the epoch
        ctx.seq = 2
        m2 = parser.parse_line("Epoch 2/8: train_loss=1.6 val_accuracy=0.51", ctx)
        assert ctx.current_epoch == 2.0
        assert all(m.epoch == 2.0 for m in m2)

    def test_epoch_key_after_the_metrics_still_stamps_them(self) -> None:
        """`epoch=N` may come LAST on the line — the metrics before it still
        belong to epoch N.

        LiveReporter.log(**kwargs) serialises in call order, so a caller writing
        log(train_loss=..., epoch=e) — and the Lightning callback, which appends
        the epoch after collecting metrics — puts the epoch at the end. Stamping
        metrics as they were scanned attributed every one to the *previous*
        epoch and dropped epoch 0 entirely (it landed as epoch=None).
        """
        ctx = ParserContext(run_id="test", seq=1)
        parser = UniversalParser()

        metrics = parser.parse_line("val_loss=0.67 val_accuracy=0.79 epoch=0", ctx)
        assert ctx.current_epoch == 0.0
        assert metrics, "expected the metrics on the line"
        assert all(m.epoch == 0.0 for m in metrics), (
            f"metrics before the epoch key got a stale epoch: {[(m.key, m.epoch) for m in metrics]}"
        )

        ctx.seq = 2
        m2 = parser.parse_line("val_loss=0.58 val_accuracy=0.82 epoch=1", ctx)
        assert all(m.epoch == 1.0 for m in m2)
        # step keys are order-independent too
        ctx.seq = 3
        m3 = parser.parse_line("loss=0.4 step=120 epoch=2", ctx)
        assert all(m.epoch == 2.0 and m.step == 120 for m in m3)
        assert not any(m.key.lower() in {"epoch", "step"} for m in m3)

    def test_never_crashes_on_garbage(self) -> None:
        ctx = ParserContext(run_id="test", seq=1)
        garbage = [
            "!!!@@@###$$$",
            "\x00\x01\x02",
            "a" * 10_000,
            "",
            "loss=nan",
            "loss=inf",
        ]
        parser = UniversalParser()
        for bad_line in garbage:
            try:
                parser.parse_line(bad_line, ctx)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"UniversalParser crashed on {bad_line!r}: {exc}")


# ------------------------------------------------------------------ registry


class TestDetectParser:
    def test_pl_wins_on_pl_log(self) -> None:
        lines = _load_lines("pytorch_lightning.log")
        parser = detect_parser(lines[:50])
        assert parser.name == "pytorch_lightning"

    def test_keras_wins_on_keras_log(self) -> None:
        lines = _load_lines("keras_image_classifier.log")
        parser = detect_parser(lines[:50])
        assert parser.name == "keras_tensorflow"

    def test_hf_wins_on_hf_log(self) -> None:
        lines = _load_lines("huggingface_bert.log")
        parser = detect_parser(lines[:50])
        assert parser.name == "huggingface"

    def test_fallback_on_unknown(self) -> None:
        parser = detect_parser(["hello world", "nothing here", "x=5"])
        assert parser.name == "universal"
