"""Regression: a pathologically long log line must not hang the parser.

The key-capture groups in the metric regexes used an unbounded ``\\w+`` which
backtracks O(n²) on a long run of word characters before a missing delimiter —
a single 100k-char line (a tensor dump, base64 blob, …) froze the pipeline for
tens of seconds. Keys are now bounded to 64 chars so matching stays linear.
"""

from __future__ import annotations

import time

import pytest

from epochix.parsers.base import ParserContext
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.pytorch_lightning import PLParser
from epochix.parsers.universal import UniversalParser

_PARSERS = [UniversalParser, KerasParser, PLParser]


@pytest.mark.parametrize("factory", _PARSERS, ids=lambda f: f.__name__)
@pytest.mark.parametrize(
    "line",
    [
        "loss=" + "9" * 100_000,  # 100k-digit value (digits are \w)
        "a" * 100_000 + " loss=0.5",  # 100k-word-char prefix
        ("x" * 60 + "=1 ") * 2000,  # many long keys
    ],
    ids=["100k_digits", "100k_words", "many_long_keys"],
)
def test_long_line_parses_fast(factory: type, line: str) -> None:
    parser = factory()
    ctx = ParserContext(run_id="t")
    start = time.perf_counter()
    parser.parse_line(line, ctx)  # must not raise or hang
    assert time.perf_counter() - start < 1.0, "parser took too long (regex backtracking?)"


def test_normal_line_still_parses() -> None:
    parser = UniversalParser()
    ctx = ParserContext(run_id="t")
    metrics = parser.parse_line("epoch=1 train_loss=0.5 val_loss=0.31 val_accuracy=0.92", ctx)
    keys = {m.key for m in metrics}
    assert {"train_loss", "val_loss", "val_accuracy"} <= keys


def test_key_at_length_limit_still_captured() -> None:
    parser = UniversalParser()
    ctx = ParserContext(run_id="t")
    key = "k" * 64  # exactly at the bound
    metrics = parser.parse_line(f"{key}=0.5", ctx)
    assert any(m.key == key for m in metrics)


def test_keras_sniff_fast_on_long_digit_run() -> None:
    """The Keras progress-bar sniff regex (\\d+/\\d+ …) backtracked O(n²) on a
    long digit run — a 200k-digit line froze detection for ~12s."""
    line = "loss=" + "9" * 200_000
    start = time.perf_counter()
    KerasParser().sniff([line] * 5)
    assert time.perf_counter() - start < 1.0


def test_parse_architecture_fast_on_long_line() -> None:
    from epochix.parsers.architecture_parser import parse_architecture

    start = time.perf_counter()
    parse_architecture(["a" * 200_000, "X" * 200_000 + " summary: 100 params"])
    assert time.perf_counter() - start < 1.0


def test_keras_progress_bar_still_detected() -> None:
    score = KerasParser().sniff(
        ["Epoch 1/50", "1563/1563 [====] - 10s - loss: 0.42 - accuracy: 0.87"]
    )
    assert score > 0.5  # a real keras log is still recognised
