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
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest

from epochix.parsers.base import ParserContext
from epochix.parsers.llm_fallback import LLMFallbackParser

if TYPE_CHECKING:
    from epochix.models import RawLogLine


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


# ── pipeline wiring: the fallback actually fires (and only when it should) ──


class _ProseIngester:
    """A log no regex parser can read — pure prose."""

    LINES = [
        "=== Training Report ===",
        "After the first pass the network reached a loss of 2.31 and classified",
        "24 percent of the validation samples correctly.",
        "Second iteration: loss fell to 1.87 while accuracy climbed to 41 percent.",
    ]

    async def lines(self) -> AsyncIterator[RawLogLine]:
        from datetime import datetime, timezone

        from epochix.models import RawLogLine

        for i, text in enumerate(self.LINES, start=1):
            yield RawLogLine(
                seq=i, timestamp=datetime.now(tz=timezone.utc), text=text, source="stdin"
            )


_FAKE_EXTRACTION = [
    {"key": "train_loss", "value": 2.31, "epoch": 1},
    {"key": "val_accuracy", "value": 0.24, "epoch": 1},
    {"key": "train_loss", "value": 1.87, "epoch": 2},
    {"key": "val_accuracy", "value": 0.41, "epoch": 2},
]


async def test_pipeline_falls_back_to_the_llm_for_unreadable_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llm_enabled + a log the regex parsers can't read → the LLM pass runs and
    its metrics flow through the normal normalize→story→store path.

    The parser was orphaned before this: not registered, never invoked, its
    final block never flushed — no user-reachable path triggered it at all.
    """
    import epochix.pipeline as pipeline
    from epochix.server.hub import Hub
    from epochix.store.sqlite_store import RunStore

    monkeypatch.setenv("EPOCHIX_LLM_ENABLED", "true")
    monkeypatch.setattr(LLMFallbackParser, "_call_llm", lambda self, text: list(_FAKE_EXTRACTION))
    monkeypatch.setattr(LLMFallbackParser, "is_available", lambda self: True)

    store = RunStore(":memory:")
    await pipeline.run_pipeline(
        ingester=_ProseIngester(), run_id="llm-fb", store=store, hub=Hub(), task=None
    )

    metrics = store.get_metric_events("llm-fb")
    assert metrics, "the LLM fallback never fired for an unreadable log"
    keys = {m.canonical_key for m in metrics}
    assert "val_accuracy" in keys and "train_loss" in keys, keys

    frames = store.get_story_frames("llm-fb")
    assert frames, "LLM-extracted metrics produced no story frames"
    assert {f.epoch for f in frames} <= {1.0, 2.0}


async def test_llm_fallback_does_not_fire_when_regex_parsers_succeed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A parseable log must never reach the LLM, even with llm_enabled."""
    from datetime import datetime, timezone

    import epochix.pipeline as pipeline
    from epochix.models import RawLogLine
    from epochix.server.hub import Hub
    from epochix.store.sqlite_store import RunStore

    monkeypatch.setenv("EPOCHIX_LLM_ENABLED", "true")
    called = []
    monkeypatch.setattr(
        LLMFallbackParser,
        "_call_llm",
        lambda self, text: called.append(text) or [],
    )

    class _KVIngester:
        async def lines(self) -> AsyncIterator[RawLogLine]:
            for e in range(1, 4):
                yield RawLogLine(
                    seq=e,
                    timestamp=datetime.now(tz=timezone.utc),
                    text=f"epoch={e} train_loss={2.0 - e * 0.3:.3f} val_accuracy={0.4 + e * 0.1:.3f}",
                    source="stdin",
                )

    store = RunStore(":memory:")
    await pipeline.run_pipeline(
        ingester=_KVIngester(), run_id="kv", store=store, hub=Hub(), task=None
    )

    assert store.get_metric_events("kv"), "sanity: the KV log parsed"
    assert not called, "the LLM was called even though the regex parsers succeeded"


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
