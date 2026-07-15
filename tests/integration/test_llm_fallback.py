"""The opt-in LLM fallback parser.

The response-parsing tests run everywhere. The end-to-end extraction test needs
a real Ollama and only runs when EPOCHIX_LLM_URL is set (see the `llm` CI job /
local Ollama), so the default suite stays offline.

Bug this pins: the Ollama call asked for `"format": "json"`, which only forces
*some* valid JSON — models collapsed a multi-metric log to a single object, and
_parse_response accepted only arrays, so the parser extracted nothing. It now
sends an explicit array schema and _parse_response tolerates a single object and
a markdown code fence.
"""

from __future__ import annotations

import os

import pytest

from epochix.parsers.base import ParserContext
from epochix.parsers.llm_fallback import LLMFallbackParser


class TestResponseParsing:
    def test_plain_array(self) -> None:
        out = LLMFallbackParser._parse_response('[{"key":"loss","value":2.3,"epoch":1}]')
        assert out == [{"key": "loss", "value": 2.3, "epoch": 1}]

    def test_single_object_collapsed_out_of_the_array(self) -> None:
        # What Ollama returns under a loose json constraint — used to yield [].
        out = LLMFallbackParser._parse_response('{"key":"loss","value":2.3,"epoch":1}')
        assert out == [{"key": "loss", "value": 2.3, "epoch": 1}]

    def test_markdown_fenced(self) -> None:
        out = LLMFallbackParser._parse_response('```json\n[{"key":"acc","value":0.9}]\n```')
        assert out == [{"key": "acc", "value": 0.9}]

    def test_nested_under_a_key(self) -> None:
        out = LLMFallbackParser._parse_response('{"metrics":[{"key":"loss","value":1.0}]}')
        assert out == [{"key": "loss", "value": 1.0}]

    @pytest.mark.parametrize(
        "raw",
        [
            "Sure! Here are the metrics.",  # prose, not JSON
            '[{"key":"loss","value":2.3',  # truncated
            "",
            "null",
            "42",
        ],
    )
    def test_malformed_degrades_to_empty(self, raw: str) -> None:
        assert LLMFallbackParser._parse_response(raw) == []

    def test_hallucinated_nulls_are_dropped_at_flush(self) -> None:
        """A row of nulls survives _parse_response but must not become a metric."""
        parser = LLMFallbackParser()
        ctx = ParserContext(run_id="t", seq=1)
        # Feed the model output directly through the flush path.
        parser._block = ["irrelevant"]
        parser._call_llm = lambda _text: [  # type: ignore[method-assign]
            {"key": None, "value": None, "epoch": None},
            {"key": "loss", "value": "not a number", "epoch": 1},
            {"key": "val_accuracy", "value": 0.8, "epoch": 2},
        ]
        metrics = parser.flush_remaining(ctx)
        # Only the one clean, numeric row survives.
        assert [(m.key, m.value) for m in metrics] == [("val_accuracy", 0.8)]


# ── live: needs a real Ollama ────────────────────────────────────────────────

_OLLAMA = os.environ.get("EPOCHIX_LLM_URL")


@pytest.mark.skipif(not _OLLAMA, reason="set EPOCHIX_LLM_URL to a running Ollama to run this")
def test_extracts_metrics_from_prose_via_real_ollama() -> None:
    """A prose log no regex parser can read → real metrics, from a real model."""
    parser = LLMFallbackParser()
    assert parser.is_available()

    prose = [
        "After the first pass the network reached a loss of 2.31 and classified",
        "24 percent of the validation samples correctly.",
        "Second iteration: loss fell to 1.87 while accuracy climbed to 41 percent.",
        "Round three concluded with loss 1.42 and 58% of samples correct.",
    ]
    ctx = ParserContext(run_id="llm", seq=0)
    for i, line in enumerate(prose):
        ctx.seq = i
        parser.parse_line(line, ctx)
    metrics = parser.flush_remaining(ctx)

    keys = {m.key.lower() for m in metrics}
    values = sorted(m.value for m in metrics)
    assert any("loss" in k for k in keys), f"no loss extracted from prose: {keys}"
    assert any("acc" in k for k in keys), f"no accuracy extracted from prose: {keys}"
    # The three loss values from the text must appear.
    assert 2.31 in values and 1.87 in values and 1.42 in values, values
