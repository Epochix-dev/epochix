"""Phase 2.4 — Hypothesis property-based fuzz tests for all parsers.

Core invariant: no parser should ever raise an exception or return
malformed data when given arbitrary text input.

Strategy:
- ``parse_line``  — single arbitrary Unicode string; context is fresh each call.
- ``sniff``       — arbitrary list of arbitrary strings (up to 100 items).
- Return types    — always ``list[RawMetric]`` / ``float`` respectively.
- Confidence      — sniff always returns a value in [0.0, 1.0].
- RawMetric shape — key is non-empty str, value is a finite float, confidence
                    is in (0.0, 1.0].

The universal parser is the primary target (it handles the widest input
surface) but including all parsers gives us broad regression coverage.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from epochix.models import RawMetric
from epochix.parsers.accelerate import AccelerateParser
from epochix.parsers.base import ParserContext
from epochix.parsers.fastai import FastAIParser
from epochix.parsers.huggingface import HFParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.pytorch_lightning import PLParser
from epochix.parsers.ultralytics_yolo import YOLOParser
from epochix.parsers.universal import UniversalParser

# ── Strategy helpers ──────────────────────────────────────────────────────────

# Arbitrary Unicode text (includes emoji, RTL, null bytes, surrogates excluded)
_text = st.text()

# Fresh ParserContext for every fuzz call
def _ctx() -> ParserContext:
    return ParserContext(run_id="fuzz", seq=1)


# ── Universal parser — primary fuzz target ────────────────────────────────────

class TestUniversalParserFuzz:
    """Property: UniversalParser never crashes on any single line."""

    _parser = UniversalParser()

    @given(line=_text)
    @settings(max_examples=2000, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_line_never_raises(self, line: str) -> None:
        result = self._parser.parse_line(line, _ctx())
        assert isinstance(result, list)

    @given(line=_text)
    @settings(max_examples=500)
    def test_parse_line_returns_list_of_raw_metrics(self, line: str) -> None:
        result = self._parser.parse_line(line, _ctx())
        for m in result:
            assert isinstance(m, RawMetric)

    @given(line=_text)
    @settings(max_examples=500)
    def test_parse_line_metric_keys_are_non_empty_strings(self, line: str) -> None:
        for m in self._parser.parse_line(line, _ctx()):
            assert isinstance(m.key, str)
            assert len(m.key) > 0

    @given(line=_text)
    @settings(max_examples=500)
    def test_parse_line_metric_values_are_finite(self, line: str) -> None:
        for m in self._parser.parse_line(line, _ctx()):
            assert isinstance(m.value, float)
            assert math.isfinite(m.value), f"Non-finite value: {m.value!r}"

    @given(line=_text)
    @settings(max_examples=500)
    def test_parse_line_confidence_in_range(self, line: str) -> None:
        for m in self._parser.parse_line(line, _ctx()):
            assert 0.0 < m.confidence <= 1.0, f"Confidence out of range: {m.confidence!r}"

    @given(lines=st.lists(_text, max_size=100))
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_sniff_never_raises(self, lines: list[str]) -> None:
        result = self._parser.sniff(lines)
        assert isinstance(result, float)

    @given(lines=st.lists(_text, max_size=100))
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_sniff_confidence_in_range(self, lines: list[str]) -> None:
        result = self._parser.sniff(lines)
        assert 0.0 <= result <= 1.0, f"sniff() returned {result!r}"

    @given(line=_text)
    @settings(max_examples=200)
    def test_context_epoch_is_float_or_none_after_parse(self, line: str) -> None:
        ctx = _ctx()
        self._parser.parse_line(line, ctx)
        assert ctx.current_epoch is None or isinstance(ctx.current_epoch, float)

    @given(line=_text)
    @settings(max_examples=200)
    def test_context_step_is_int_or_none_after_parse(self, line: str) -> None:
        ctx = _ctx()
        self._parser.parse_line(line, ctx)
        assert ctx.current_step is None or isinstance(ctx.current_step, int)

    @given(
        lines=st.lists(_text, min_size=1, max_size=20),
    )
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_sequential_parse_never_raises(self, lines: list[str]) -> None:
        """Multiple sequential lines sharing a context must not crash."""
        ctx = ParserContext(run_id="seq-fuzz", seq=0)
        for line in lines:
            ctx.seq += 1
            result = self._parser.parse_line(line, ctx)
            assert isinstance(result, list)


# ── All parsers — sniff invariants ────────────────────────────────────────────

_ALL_PARSERS = [
    PLParser(),
    KerasParser(),
    HFParser(),
    YOLOParser(),
    FastAIParser(),
    AccelerateParser(),
    UniversalParser(),
]


class TestAllParsersSniffFuzz:
    """sniff() on every parser must be safe and return [0, 1]."""

    @pytest.mark.parametrize("parser", _ALL_PARSERS, ids=lambda p: p.name)
    @given(lines=st.lists(_text, max_size=60))
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_sniff_never_raises(self, parser: object, lines: list[str]) -> None:
        from epochix.parsers.base import BaseParser
        assert isinstance(parser, BaseParser)
        result = parser.sniff(lines)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestAllParsersParseLineFuzz:
    """parse_line() on every parser must never raise on arbitrary input."""

    @pytest.mark.parametrize("parser", _ALL_PARSERS, ids=lambda p: p.name)
    @given(line=_text)
    @settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_line_never_raises(self, parser: object, line: str) -> None:
        from epochix.parsers.base import BaseParser
        assert isinstance(parser, BaseParser)
        result = parser.parse_line(line, _ctx())
        assert isinstance(result, list)
        for m in result:
            assert isinstance(m, RawMetric)
            assert isinstance(m.key, str) and m.key
            assert math.isfinite(m.value)


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestUniversalParserEdgeCases:
    """Hand-crafted edge cases that historically trip up regex-based parsers."""

    _p = UniversalParser()

    @pytest.mark.parametrize("line", [
        "",                                   # empty string
        " ",                                  # whitespace only
        "\n\r\t",                             # control characters
        "=",                                  # bare equals
        ":",                                  # bare colon
        "{",                                  # unclosed brace
        "{}",                                 # empty dict
        "{'key': None}",                      # None value
        '{"key": "string_value"}',            # string value in JSON
        '{"key": 1e308}',                     # extreme float
        '{"key": -1e308}',                    # extreme negative float
        '{"key": 0}',                         # zero
        "loss=nan",                           # nan value string
        "loss=inf",                           # inf value string
        "loss=-inf",                          # -inf value string
        "a=1 b=2 c=3 d=4 e=5 f=6 g=7",       # many kv pairs
        "epoch=0",                            # epoch zero
        "epoch=-1",                           # negative epoch
        "step=999999",                        # large step
        "key" * 200,                          # very long key
        "=" * 200,                            # many equals
        "{" + "a:1," * 50 + "}",              # large dict-ish
        "\x00\x01\x02\x03",                   # null and control chars
        "🚀 loss=0.5 🎯 accuracy=0.9 🏆",     # emoji
        "val_accuracy: 0.950",                # colon pattern
        "loss: 0.3, val_loss: 0.5",           # two colon patterns
        "step 100/1000 loss 0.456",           # no separator
    ])
    def test_known_edge_case_does_not_raise(self, line: str) -> None:
        result = self._p.parse_line(line, _ctx())
        assert isinstance(result, list)
        for m in result:
            assert math.isfinite(m.value), f"line={line!r} → {m.value!r}"
