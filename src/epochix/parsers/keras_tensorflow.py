from __future__ import annotations

import contextlib
import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import register_parser

# Epoch header: "Epoch 1/50"
_EPOCH_LINE = re.compile(r"^Epoch\s+(\d+)/(\d+)\s*$")
# Progress bar metric: "1563/1563 [====] - 10s - loss: 0.423 - accuracy: 0.867"
_METRIC_LINE = re.compile(r"\d+/\d+\s+\[=+>?\.*\]")
_KV_PAIR = re.compile(r"(\w+):\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")

_SKIP_KEYS = frozenset({"s", "ms", "us"})


@register_parser
class KerasParser:
    name = "keras_tensorflow"
    priority = 85

    def sniff(self, sample_lines: list[str]) -> float:
        has_epoch = any(_EPOCH_LINE.match(line) for line in sample_lines)
        has_bar = any(_METRIC_LINE.search(line) for line in sample_lines)
        if has_epoch and has_bar:
            return 0.92
        if has_epoch or has_bar:
            return 0.45
        return 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        m = _EPOCH_LINE.match(line.strip())
        if m:
            ctx.current_epoch = float(m.group(1))
            ctx.total_epochs = int(m.group(2))
            return []

        metrics: list[RawMetric] = []
        for kv in _KV_PAIR.finditer(line):
            key, val = kv.group(1), kv.group(2)
            if key.lower() in _SKIP_KEYS:
                continue
            with contextlib.suppress(ValueError):
                metrics.append(
                    RawMetric(
                        seq=ctx.seq,
                        epoch=ctx.current_epoch,
                        step=ctx.current_step,
                        key=key,
                        value=float(val),
                        parser_name=self.name,
                        confidence=0.88,
                    )
                )
        return metrics
