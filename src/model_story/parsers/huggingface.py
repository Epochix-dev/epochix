from __future__ import annotations

import json
import re

from model_story.models import RawMetric
from model_story.parsers.base import ParserContext
from model_story.parsers.registry import register_parser

# HF Trainer logs a JSON-like dict per step/eval:
#   {'loss': 0.5123, 'learning_rate': 5e-05, 'epoch': 1.0}
#   {'eval_loss': 0.3421, 'eval_accuracy': 0.8765, 'epoch': 1.0}
_HF_DICT_LINE = re.compile(r"^\s*\{['\"]loss['\"].*\}")


@register_parser
class HFParser:
    name = "huggingface"
    priority = 80

    def sniff(self, sample_lines: list[str]) -> float:
        hits = sum(1 for line in sample_lines if _HF_DICT_LINE.match(line))
        return min(hits / max(len(sample_lines), 1) * 5, 0.93)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        stripped = line.strip()
        if not stripped.startswith("{"):
            return []

        # Normalize Python dict literals to valid JSON
        normalized = stripped.replace("'", '"').replace("True", "true").replace("False", "false")
        try:
            data: dict[str, object] = json.loads(normalized)
        except json.JSONDecodeError:
            return []

        epoch = data.pop("epoch", None)
        if epoch is not None and isinstance(epoch, (int, float)):
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
                    confidence=0.91,
                )
            )
        return metrics
