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


def _time_parse(factory: type, line: str) -> float:
    """Best of three — a shared CI runner gets descheduled mid-measurement."""
    best = float("inf")
    for _ in range(3):
        parser = factory()
        ctx = ParserContext(run_id="t")
        start = time.perf_counter()
        parser.parse_line(line, ctx)  # must not raise or hang
        best = min(best, time.perf_counter() - start)
    return best


_LINES = {
    "digits": lambda n: "loss=" + "9" * (25_000 * n),  # digits are \w
    "words": lambda n: "a" * (25_000 * n) + " loss=0.5",
    "long_keys": lambda n: ("x" * 60 + "=1 ") * (500 * n),
}


@pytest.mark.parametrize("factory", _PARSERS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("shape", list(_LINES), ids=list(_LINES))
def test_long_line_scales_linearly(factory: type, shape: str) -> None:
    """Catastrophic backtracking is *superlinear growth*, not slowness.

    This asserted a flat 1.0 s wall-clock budget and went red on a Windows CI
    runner that took 2.44 s — where the same input parses in 0.04 s locally and
    scales perfectly linearly. The test was measuring how busy the runner was,
    not how the regex behaves.

    Quadrupling the input multiplies a linear scan by ~4 and a quadratic
    blow-up by ~16, and that ratio holds however slow the machine is. The
    allowance below sits well clear of 4 and well under 16.
    """
    make = _LINES[shape]
    small = _time_parse(factory, make(1))
    large = _time_parse(factory, make(4))

    # The additive term keeps sub-millisecond baselines from making the ratio
    # meaningless; the multiplier is what actually catches backtracking.
    assert large < small * 9 + 0.05, (
        f"{factory.__name__} on {shape}: {small:.4f}s → {large:.4f}s for 4x the "
        f"input ({large / max(small, 1e-9):.1f}x). Linear would be ~4x; "
        f"quadratic backtracking ~16x."
    )


@pytest.mark.parametrize("factory", _PARSERS, ids=lambda f: f.__name__)
def test_a_pathological_line_never_hangs(factory: type) -> None:
    """A generous ceiling purely as a hang guard — a real ReDoS on these
    inputs took tens of seconds, so this catches it even on slow hardware
    without failing merely because the runner is loaded."""
    assert _time_parse(factory, ("x" * 60 + "=1 ") * 2000) < 20.0


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
    # A hang guard, not a performance budget: the bug this covers took ~12 s,
    # so a loaded CI runner has room without the test crying wolf.
    assert time.perf_counter() - start < 20.0


def test_parse_architecture_fast_on_long_line() -> None:
    from epochix.parsers.architecture_parser import parse_architecture

    start = time.perf_counter()
    parse_architecture(["a" * 200_000, "X" * 200_000 + " summary: 100 params"])
    assert time.perf_counter() - start < 20.0  # hang guard, see above


def test_keras_progress_bar_still_detected() -> None:
    score = KerasParser().sniff(
        ["Epoch 1/50", "1563/1563 [====] - 10s - loss: 0.42 - accuracy: 0.87"]
    )
    assert score > 0.5  # a real keras log is still recognised
