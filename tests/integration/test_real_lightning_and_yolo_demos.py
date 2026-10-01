"""The bundled demos are recorded runs, and Epochix reads them as the libraries print them.

Two of the three demos `epochix demo` plays were written by hand, in the shape
the parsers expected. Recording real runs to replace them showed what that had
hidden:

* **PyTorch Lightning's own output was not read at all.** The parser accepted
  only `Epoch 3/10:`; Lightning prints `Epoch 3:` (counting from 0), and the
  universal parser skips progress bars by design. No metric, no frame, no
  story, and its newer boxed model summary matched nothing either.
* **A real Ultralytics run was told as segmentation.** Ultralytics prints its
  whole configuration on one line; `iou=0.7`, a threshold, became the run's
  IoU. And the validation of `best.pt` after training was counted as one more
  epoch.

Both logs are the libraries' console output, byte for byte (`demo/*_source.py`).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import Run, StoryFrame
from epochix.parsers.base import ParserContext
from epochix.parsers.pytorch_lightning import PLParser
from epochix.parsers.universal import UniversalParser, is_config_dump
from epochix.pipeline import _clean_line, run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

DEMO = Path(__file__).resolve().parents[2] / "demo"
SEQ2SEQ = DEMO / "seq2seq_attention.log"
YOLO = DEMO / "yolov8_detection.log"

# Validation token accuracy after each of the 20 epochs, as Lightning printed it.
SEQ2SEQ_VAL_ACC = [
    0.614, 0.661, 0.704, 0.733, 0.755, 0.776, 0.788, 0.800, 0.801, 0.813,
    0.816, 0.822, 0.822, 0.820, 0.822, 0.824, 0.823, 0.824, 0.822, 0.823,
]  # fmt: skip


def _told(log: Path) -> tuple[Run, list[StoryFrame], RunStore]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("d", str(log)), run_id="d", store=store, hub=Hub())
    )
    return run, store.get_story_frames("d"), store


def _cleaned(log: Path) -> list[str]:
    raw = log.read_bytes().decode("utf-8")
    return [c for c in (_clean_line(ln) for ln in raw.split("\n")) if c.strip()]


# ── the demos carry nothing about the machine that recorded them ─────────────


@pytest.mark.parametrize("log", [SEQ2SEQ, YOLO], ids=lambda p: p.name)
def test_a_demo_log_names_no_user_or_home_folder(log: Path) -> None:
    """The captures these replaced had been recorded from a scratch folder and
    shipped its path, user name included."""
    text = log.read_bytes().decode("utf-8")
    assert not re.search(r"[\\/]Users[\\/]|AppData|[\\/]home[\\/]", text)
    assert (DEMO / f"{log.stem}_source.py").is_file()
    assert b"\r" in log.read_bytes(), "a real progress bar redraws its line"


# ── Lightning ────────────────────────────────────────────────────────────────


def test_the_real_lightning_run_is_read_epoch_by_epoch() -> None:
    run, frames, store = _told(SEQ2SEQ)
    assert run.parser_used == "pytorch_lightning"
    assert run.primary_metric == "val_accuracy"
    assert [f.epoch for f in frames] == [float(e) for e in range(1, 21)]
    assert [f.primary_metric_value for f in frames] == pytest.approx(SEQ2SEQ_VAL_ACC)
    # `v_num` and the stopping condition are not metrics.
    keys = {e.canonical_key for e in store.get_metric_events("d")}
    assert keys == {"accuracy", "train_loss", "val_accuracy", "val_loss"}
    # Lightning says how long the run was only when it stops.
    assert frames[-1].progress == pytest.approx(1.0)


def test_its_boxed_model_summary_is_read() -> None:
    run, _, _ = _told(SEQ2SEQ)
    layers = (run.config or {})["architecture"]
    assert [(lyr["name"], lyr["layer_type"]) for lyr in layers] == [
        ("src_embedding", "Embedding"),
        ("encoder", "GRU"),
        ("tgt_embedding", "Embedding"),
        ("attention", "BahdanauAttention"),
        ("decoder", "GRU"),
        ("head", "Linear"),
        ("dropout", "Dropout"),
    ]
    assert layers[1]["params"] == 394_000


def test_its_overfitting_is_seen() -> None:
    """Validation loss bottoms out near epoch 13 and rises while training loss
    keeps falling — a real, mild overfit, and the reason to show this run."""
    _, frames, _ = _told(SEQ2SEQ)
    overfit = [f.epoch for f in frames for w in f.warnings if w.kind == "overfit"]
    assert overfit and min(overfit) >= 14, overfit


def _lightning(n: int, done: int, total: int, postfix: str) -> str:
    bar = "#" * 10 if done == total else "###       "
    pct = round(100 * done / total)
    return f"Epoch {n}: {pct}%|{bar}| {done}/{total} [00:03<00:00, 38.67it/s{postfix}]"


class TestLightningLines:
    def _parse(self, lines: list[str]) -> list[tuple[float | None, str, float]]:
        parser, ctx = PLParser(), ParserContext(run_id="t")
        out = []
        for line in lines:
            out += [(m.epoch, m.key, m.value) for m in parser.parse_line(line, ctx)]
        return out

    def test_the_bar_for_epoch_n_carries_the_epoch_before_its_results(self) -> None:
        got = self._parse(
            [
                _lightning(0, 148, 148, ""),
                _lightning(1, 148, 148, ", v_num=0, val_loss=2.330, val_acc=0.614"),
                _lightning(2, 148, 148, ", v_num=0, val_loss=1.920, val_acc=0.661"),
            ]
        )
        assert got == [
            (1.0, "val_loss", 2.33),
            (1.0, "val_acc", 0.614),
            (2.0, "val_loss", 1.92),
            (2.0, "val_acc", 0.661),
        ]

    def test_the_last_epoch_s_redraw_is_one_more_epoch_and_a_repeat_is_not(self) -> None:
        last = ", val_loss=1.100, val_acc=0.823"
        got = self._parse(
            [
                _lightning(19, 148, 148, ", val_loss=1.090, val_acc=0.822"),
                _lightning(19, 148, 148, last) + "`Trainer.fit` stopped: `max_epochs=20` reached.",
                _lightning(19, 148, 148, last),
            ]
        )
        assert [(e, k) for e, k, _ in got] == [
            (19.0, "val_loss"),
            (19.0, "val_acc"),
            (20.0, "val_loss"),
            (20.0, "val_acc"),
        ]

    def test_a_bar_caught_mid_epoch_is_not_a_result(self) -> None:
        assert self._parse([_lightning(3, 60, 148, ", val_loss=1.660, val_acc=0.704")]) == []

    def test_the_stopping_condition_sets_the_length_of_the_run(self) -> None:
        parser, ctx = PLParser(), ParserContext(run_id="t")
        line = _lightning(19, 148, 148, ", val_acc=0.823")
        parser.parse_line(line + "`Trainer.fit` stopped: `max_epochs=20` reached.", ctx)
        assert ctx.total_epochs == 20

    def test_a_hand_written_tqdm_loop_reads_as_before(self) -> None:
        line = "Epoch 5/30: 100%|████| 250/250 [00:13<00:00, loss=0.821, acc=0.612]"
        parser, ctx = PLParser(), ParserContext(run_id="t")
        got = [(m.epoch, m.key, m.value) for m in parser.parse_line(line, ctx)]
        assert got == [(5.0, "loss", 0.821), (5.0, "acc", 0.612)]
        assert ctx.total_epochs == 30

    def test_a_real_log_is_recognised_from_its_first_lines(self) -> None:
        """Preamble and validation bars outnumber the epoch lines; counting
        epoch lines alone left it under the detection threshold."""
        from epochix.parsers.registry import SNIFF_SAMPLE_LINES, SNIFF_THRESHOLD, detect_parser

        sample = _cleaned(SEQ2SEQ)[:SNIFF_SAMPLE_LINES]
        assert PLParser().sniff(sample) > SNIFF_THRESHOLD
        assert detect_parser(sample).name == "pytorch_lightning"


# ── Ultralytics ──────────────────────────────────────────────────────────────


def test_the_real_yolo_run_is_a_detection_run_told_on_map50() -> None:
    run, frames, store = _told(YOLO)
    assert run.parser_used == "ultralytics_yolo"
    assert run.task_type is not None and run.task_type.value == "detection"
    assert run.primary_metric == "mAP50"
    keys = {e.canonical_key for e in store.get_metric_events("d")}
    assert "IoU" not in keys, "a setting (`iou=0.7`) was read as a metric"
    told = [f for f in frames if f.primary_metric == "mAP50"]
    assert [f.epoch for f in told] == [float(e) for e in range(1, 31)]
    assert told[0].primary_metric_value == pytest.approx(0.619)
    assert told[-1].primary_metric_value == pytest.approx(0.816)


def test_validating_the_best_checkpoint_is_not_another_epoch() -> None:
    lines = _cleaned(YOLO)
    final = next(i for i, ln in enumerate(lines) if ln.startswith("Validating "))
    assert any(re.match(r"\s*all\s+\d+\s+\d+", ln) for ln in lines[final:]), (
        "the fixture has no final validation row to test"
    )
    _, frames, _ = _told(YOLO)
    assert max(f.epoch for f in frames if f.epoch is not None) == 30.0
    assert sum(1 for f in frames if f.epoch == 30.0) == 1


class TestSettingsDump:
    def test_the_real_settings_line_yields_no_metric(self) -> None:
        line = next(ln for ln in _cleaned(YOLO) if "trainer:" in ln and "iou=" in ln)
        assert line.count("=") > 50
        assert is_config_dump(line)
        assert UniversalParser().parse_line(line, ParserContext(run_id="t")) == []

    def test_an_argparse_namespace_is_one_too(self) -> None:
        line = (
            "Namespace(lr=0.1, epochs=30, batch_size=256, model='resnet18', amp=True, "
            "iou=0.5, workers=8, seed=7, data='cifar10', optimizer='sgd', resume=None, "
            "cosine=False, wd=0.0005)"
        )
        assert is_config_dump(line)

    def test_a_wide_line_of_metrics_is_not(self) -> None:
        line = (
            "epoch=3 train_loss=0.41 val_loss=0.52 acc=0.81 val_acc=0.79 f1=0.77 precision=0.80 "
            "recall=0.75 lr=0.001 auc=0.91 iou=0.66 dice=0.74 mae=0.12 rmse=0.2"
        )
        assert not is_config_dump(line)
        keys = {m.key for m in UniversalParser().parse_line(line, ParserContext(run_id="t"))}
        assert {"val_loss", "iou", "val_acc"} <= keys
