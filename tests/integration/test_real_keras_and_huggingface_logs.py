"""Real Keras 3 and Hugging Face Trainer output.

Every Keras and Hugging Face fixture had been written by hand, in the layouts
older versions printed. The "Keras demo" was a real training run whose script
*printed* Keras 2's lines itself. Recorded from the libraries:

* **Keras 3**, written to a file, puts every progress update on its own line.
  Each partial bar ("12/43 ━━━ ... accuracy: 0.1172") was read as a reading;
  and when the Keras parser was made to decline them, the fallback parsers
  read them instead. It also prints the finished bar twice when there is
  validation data.
* **The Hugging Face Trainer** (transformers 5) prints its numbers as strings —
  `{'loss': '1.925', 'epoch': '1'}`. Only bare numbers were accepted: a real
  log produced no metric at all. Its timing fields were not metrics either,
  and its end-of-run summary carries the run's *average* loss.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import Run, StoryFrame
from epochix.parsers.base import LINE_CLAIMED, ParserContext
from epochix.parsers.huggingface import HFParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.pipeline import _clean_line, run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

REPO = Path(__file__).resolve().parents[2]
KERAS_BAR = REPO / "demo" / "keras_image_classifier.log"
KERAS_LINES = REPO / "tests" / "fixtures" / "logs" / "keras_real_verbose2.log"
VSCODE_DEMO = REPO / "epochix-vscode" / "media" / "demo.log"
HF = REPO / "tests" / "fixtures" / "logs" / "huggingface_real_trainer.log"


def _told(log: Path) -> tuple[Run, list[StoryFrame], Counter[str]]:
    assert log.stat().st_size > 0
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("k", str(log)), run_id="k", store=store, hub=Hub())
    )
    counts = Counter(e.canonical_key for e in store.get_metric_events("k"))
    return run, store.get_story_frames("k"), counts


def _cleaned(log: Path) -> list[str]:
    raw = log.read_bytes().decode("utf-8")
    return [c for c in (_clean_line(ln) for ln in raw.split("\n")) if c.strip()]


# ── Keras ────────────────────────────────────────────────────────────────────


def test_the_keras_demo_is_keras_s_own_output() -> None:
    lines = _cleaned(KERAS_BAR)
    assert any("━" in ln for ln in lines), "not a Keras 3 progress bar"
    partial = [ln for ln in lines if ln.strip().startswith("12/43")]
    assert partial, "the capture has no mid-epoch progress lines to test"
    source = (REPO / "demo" / "keras_image_classifier_source.py").read_text(encoding="utf-8")
    assert "import keras" in source and "model.fit(" in source


@pytest.mark.parametrize("log", [KERAS_BAR, KERAS_LINES], ids=["progress_bar", "one_line"])
def test_one_reading_per_epoch_whichever_way_keras_logged(log: Path) -> None:
    run, frames, counts = _told(log)
    assert run.parser_used == "keras_tensorflow"
    assert [f.epoch for f in frames] == [float(e) for e in range(1, 21)]
    assert {f.primary_metric for f in frames} == {"val_accuracy"}
    # No partial bar, and the finished bar's repeat is not a second reading.
    assert dict(counts) == {"accuracy": 20, "train_loss": 20, "val_accuracy": 20, "val_loss": 20}
    assert frames[-1].primary_metric_value == pytest.approx(0.9578)


def test_both_ways_tell_the_same_run() -> None:
    _, bar, _ = _told(KERAS_BAR)
    _, lines, _ = _told(KERAS_LINES)
    assert [f.primary_metric_value for f in bar] == [f.primary_metric_value for f in lines]


def test_keras_3_s_boxed_summary_is_read() -> None:
    run, _, _ = _told(KERAS_BAR)
    layers = (run.config or {})["architecture"]
    assert [(lyr["name"], lyr["layer_type"], lyr["params"]) for lyr in layers] == [
        ("conv2d", "Conv2D", 160),
        ("max_pooling2d", "MaxPooling2D", 0),
        ("dense", "Dense", 8224),
        ("dense_1", "Dense", 330),
    ]


def test_the_extension_s_demo_carries_its_learning_rate_schedule() -> None:
    run, frames, counts = _told(VSCODE_DEMO)
    assert counts["lr"] == 20, "the cosine schedule Keras printed was not read"
    assert frames[-1].primary_metric_value == pytest.approx(0.9844)
    assert len((run.config or {})["architecture"]) == 7


class TestKerasLines:
    BAR = "━" * 20

    def test_a_partial_bar_is_declined_and_claimed(self) -> None:
        parser, ctx = KerasParser(), ParserContext(run_id="t")
        parser.parse_line("Epoch 1/20", ctx)
        line = f"12/43 {self.BAR} 0s 5ms/step - accuracy: 0.1172 - loss: 2.3113"
        assert parser.parse_line(line, ctx) == []
        assert ctx.extra.get(LINE_CLAIMED) is True, "the fallback parsers would read it"

    def test_the_repeated_finished_bar_adds_only_what_is_new(self) -> None:
        parser, ctx = KerasParser(), ParserContext(run_id="t")
        parser.parse_line("Epoch 1/20", ctx)
        first = parser.parse_line(
            f"43/43 {self.BAR} 0s 8ms/step - accuracy: 0.1359 - loss: 2.2755", ctx
        )
        again = parser.parse_line(
            f"43/43 {self.BAR} 12s 9ms/step - accuracy: 0.1359 - loss: 2.2755"
            " - val_accuracy: 0.2978 - val_loss: 2.2277",
            ctx,
        )
        assert [m.key for m in first] == ["accuracy", "loss"]
        assert [m.key for m in again] == ["val_accuracy", "val_loss"]

    def test_the_same_value_next_epoch_is_a_new_reading(self) -> None:
        parser, ctx = KerasParser(), ParserContext(run_id="t")
        for epoch in (1, 2):
            parser.parse_line(f"Epoch {epoch}/20", ctx)
            got = parser.parse_line("43/43 - 0s - 5ms/step - accuracy: 0.5 - loss: 1.0", ctx)
            assert [m.key for m in got] == ["accuracy", "loss"], epoch

    def test_keras_2_s_layout_reads_as_before(self) -> None:
        parser, ctx = KerasParser(), ParserContext(run_id="t")
        parser.parse_line("Epoch 3/50", ctx)
        line = (
            "1563/1563 [==============================] - 8s 5ms/step - loss: 0.42 - accuracy: 0.86"
        )
        assert [(m.epoch, m.key, m.value) for m in parser.parse_line(line, ctx)] == [
            (3.0, "loss", 0.42),
            (3.0, "accuracy", 0.86),
        ]
        partial = (
            "  64/1563 [>.............................] - ETA: 7s - loss: 2.31 - accuracy: 0.10"
        )
        assert parser.parse_line(partial, ctx) == []


# ── Hugging Face ─────────────────────────────────────────────────────────────


def test_a_real_trainer_log_is_read() -> None:
    assert "{'loss': '" in HF.read_text(encoding="utf-8"), "the fixture's numbers are not quoted"
    run, frames, counts = _told(HF)
    assert run.parser_used == "huggingface"
    assert run.primary_metric == "val_accuracy"
    told = [f for f in frames if f.primary_metric == "val_accuracy"]
    assert [f.epoch for f in told] == [float(e) for e in range(1, 11)]
    assert told[0].primary_metric_value == pytest.approx(0.8178)
    assert told[-1].primary_metric_value == pytest.approx(0.9444)
    # Ten epochs of each — the end-of-run summary's average loss is not an 11th.
    assert counts["train_loss"] == 10 and counts["val_loss"] == 10
    # How fast evaluation ran is not a metric.
    assert not [k for k in counts if "runtime" in k or "per_second" in k], counts


class TestTrainerDicts:
    def _parse(self, line: str) -> tuple[list[tuple[str, float]], ParserContext]:
        ctx = ParserContext(run_id="t")
        return [(m.key, m.value) for m in HFParser().parse_line(line, ctx)], ctx

    def test_quoted_numbers_are_numbers(self) -> None:
        got, ctx = self._parse("{'loss': '0.9596', 'learning_rate': '6.977e-06', 'epoch': '2'}")
        assert got == [("loss", 0.9596), ("learning_rate", 6.977e-06)]
        assert ctx.current_epoch == 2.0

    def test_bare_numbers_read_as_before(self) -> None:
        got, ctx = self._parse("{'eval_loss': 0.3421, 'eval_accuracy': 0.8765, 'epoch': 1.0}")
        assert got == [("eval_loss", 0.3421), ("eval_accuracy", 0.8765)]
        assert ctx.current_epoch == 1.0

    def test_a_quoted_word_is_not_a_number(self) -> None:
        got, _ = self._parse("{'loss': '0.5', 'model': 'bert-base', 'ok': True, 'epoch': '1'}")
        assert got == [("loss", 0.5)]

    def test_the_end_of_run_summary_is_declined_and_claimed(self) -> None:
        line = (
            "{'train_runtime': '9.366', 'train_samples_per_second': '1438', "
            "'train_loss': '0.5059', 'epoch': '10'}"
        )
        got, ctx = self._parse(line)
        assert got == []
        assert ctx.extra.get(LINE_CLAIMED) is True
