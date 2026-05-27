from __future__ import annotations

import contextlib
import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import register_parser

# Matches lines like:
#   Epoch 3/10: 100%|████| 250/250 [00:12<00:00, loss=0.432, acc=0.867]
_EPOCH_HEADER = re.compile(r"Epoch\s+(\d+)/(\d+)")
_KV_PAIR = re.compile(r"(\w+)\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
_PROGRESS_LINE = re.compile(r"Epoch\s+\d+/\d+:.*\|")

_SKIP_KEYS = frozenset({"epoch", "step", "it"})


@register_parser
class PLParser:
    name = "pytorch_lightning"
    priority = 90

    def sniff(self, sample_lines: list[str]) -> float:
        matches = sum(1 for line in sample_lines if _PROGRESS_LINE.search(line))
        return min(matches / max(len(sample_lines), 1) * 3, 0.95)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        # Update epoch from header
        m = _EPOCH_HEADER.search(line)
        if m:
            ctx.current_epoch = float(m.group(1))
            ctx.total_epochs = int(m.group(2))
        else:
            # No epoch header → this is not a training-progress line. Skip
            # metric extraction so config/trailer lines such as
            # "`Trainer.fit` stopped: `max_epochs=30` reached." aren't parsed
            # as bogus 'custom' metrics.
            return []

        metrics: list[RawMetric] = []
        if not _KV_PAIR.search(line):
            return metrics

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
                        confidence=0.90,
                    )
                )
        return metrics
