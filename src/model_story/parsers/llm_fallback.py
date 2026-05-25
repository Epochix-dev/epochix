"""LLM fallback parser — Ollama / OpenAI batch extraction.

This parser is the last resort for log formats that none of the
regex-based parsers can handle.  It batches lines into blocks of up to
``BLOCK_LINES`` and submits them to a local Ollama instance (or OpenAI
if configured) asking for a JSON list of ``{key, value, epoch}`` objects.

Opt-in only — **never enabled by default**.  Users must set either:
- ``MODEL_STORY_LLM_URL`` (Ollama endpoint, e.g. ``http://localhost:11434``)
- ``MODEL_STORY_LLM_KEY`` (OpenAI API key)

in their environment or ``.model-story.yaml`` config.

Usage::

    from model_story.parsers.llm_fallback import LLMFallbackParser
    # Register with the global registry:
    from model_story.parsers.registry import register_parser
    register_parser(LLMFallbackParser)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from model_story.models import RawMetric
from model_story.parsers.base import ParserContext

logger = logging.getLogger(__name__)

BLOCK_LINES = 20  # Lines submitted per LLM call
_PROMPT_TEMPLATE = """\
You are a metric extractor. I will give you lines from a machine learning training log.
Extract all numeric training metrics and return ONLY valid JSON — an array of objects.
Each object must have exactly these keys:
  "key":   metric name (string, snake_case)
  "value": numeric value (number, not string)
  "epoch": current epoch if detectable (number or null)

Return [] if no metrics are found. No explanation, no markdown, only the JSON array.

LOG LINES:
{lines}
"""


class LLMFallbackParser:
    """LLM-powered fallback parser (opt-in, requires Ollama or OpenAI)."""

    name = "llm_fallback"
    priority = 0  # even lower than universal — true last resort

    def __init__(self) -> None:
        self._llm_url = os.environ.get("MODEL_STORY_LLM_URL", "")
        self._llm_key = os.environ.get("MODEL_STORY_LLM_KEY", "")
        self._model = os.environ.get("MODEL_STORY_LLM_MODEL", "llama3")
        self._block: list[str] = []
        self._pending: list[tuple[int, int]] = []  # (seq, block_start_seq)

    def sniff(self, sample_lines: list[str]) -> float:  # noqa: ARG002
        """Always 0 — this parser must be explicitly enabled."""
        return 0.0

    def is_available(self) -> bool:
        """Return True if an LLM backend is configured."""
        return bool(self._llm_url or self._llm_key)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        """Accumulate lines; flush and call LLM every BLOCK_LINES lines."""
        self._block.append(line)
        self._pending.append((ctx.seq, ctx.seq - len(self._block) + 1))

        if len(self._block) < BLOCK_LINES:
            return []

        return self._flush(ctx)

    def flush_remaining(self, ctx: ParserContext) -> list[RawMetric]:
        """Call at end of file to process any remaining buffered lines."""
        if not self._block:
            return []
        return self._flush(ctx)

    # ── Private ───────────────────────────────────────────────────────────────

    def _flush(self, ctx: ParserContext) -> list[RawMetric]:
        block = self._block[:]
        self._block.clear()
        self._pending.clear()

        try:
            extracted = self._call_llm("\n".join(block))
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM fallback call failed: %s", exc)
            return []

        metrics: list[RawMetric] = []
        for item in extracted:
            key = str(item.get("key", "")).strip()
            raw_val = item.get("value")
            epoch = item.get("epoch")
            if not key or raw_val is None:
                continue
            try:
                value = float(raw_val)
                ep = float(epoch) if epoch is not None else ctx.current_epoch
            except (TypeError, ValueError):
                continue
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ep,
                    step=ctx.current_step,
                    key=key,
                    value=value,
                    parser_name=self.name,
                    confidence=0.55,  # LLM output is less reliable than regex
                )
            )
        return metrics

    def _call_llm(self, lines_text: str) -> list[dict[str, Any]]:
        """Call Ollama or OpenAI and return parsed JSON list."""
        prompt = _PROMPT_TEMPLATE.format(lines=lines_text)

        if self._llm_key:
            return self._call_openai(prompt)
        if self._llm_url:
            return self._call_ollama(prompt)
        return []

    def _call_ollama(self, prompt: str) -> list[dict[str, Any]]:
        url = self._llm_url.rstrip("/") + "/api/generate"
        payload = json.dumps({
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        raw = data.get("response", "[]")
        return self._parse_response(raw)

    def _call_openai(self, prompt: str) -> list[dict[str, Any]]:
        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": os.environ.get("MODEL_STORY_LLM_MODEL", "gpt-4o-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._llm_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        raw = data["choices"][0]["message"]["content"]
        return self._parse_response(raw)

    @staticmethod
    def _parse_response(raw: str) -> list[dict[str, Any]]:
        """Parse JSON array from LLM response; tolerate wrapped objects."""
        raw = raw.strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [d for d in parsed if isinstance(d, dict)]
        if isinstance(parsed, dict):
            # Some models return {"metrics": [...]}
            for v in parsed.values():
                if isinstance(v, list):
                    return [d for d in v if isinstance(d, dict)]
        return []
