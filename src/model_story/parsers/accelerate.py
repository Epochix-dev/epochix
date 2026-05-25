from __future__ import annotations

import json
import re

from model_story.models import RawMetric
from model_story.parsers.base import ParserContext
from model_story.parsers.registry import register_parser

# Accelerate uses HuggingFace Trainer under the hood but may also emit
# step-based logs via `accelerate.logging` with different keys.
# Primary signal: JSON dicts with 'loss' or 'eval_loss' and a 'step' key.
_ACCEL_DICT = re.compile(r"^\s*\{['\"](?:loss|eval_loss)['\"].*['\"]step['\"]")


@register_parser
class AccelerateParser:
    name = "accelerate"
    priority = 78

    def sniff(self, sample_lines: list[str]) -> float:
        hits = sum(1 for line in sample_lines if _ACCEL_DICT.match(line))
        return min(hits / max(len(sample_lines), 1) * 5, 0.88)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        stripped = line.strip()
        if not stripped.startswith("{"):
            return []

        normalized = stripped.replace("'", '"').replace("True", "true").replace("False", "false")
        try:
            data: dict[str, object] = json.loads(normalized)
        except json.JSONDecodeError:
            return []

        step = data.pop("step", None)
        if isinstance(step, (int, float)):
            ctx.current_step = int(step)

        epoch = data.pop("epoch", None)
        if isinstance(epoch, (int, float)):
            ctx.current_epoch = float(epoch)

        metrics: list[RawMetric] = []
        for key, val in data.items():
            if not isinstance(val, (int, float)):
                continue
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    step=ctx.current_step,
                    key=key,
                    value=float(val),
                    parser_name=self.name,
                    confidence=0.85,
                )
            )
        return metrics
