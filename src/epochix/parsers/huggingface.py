from __future__ import annotations

import json
import re

from epochix.models import RawMetric
from epochix.parsers._never_metrics import NEVER_METRICS
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

# HF Trainer logs a dict per logging step and per evaluation. Older versions
# print the numbers bare; current ones (transformers 5) print them as strings:
#   {'loss': 0.5123, 'learning_rate': 5e-05, 'epoch': 1.0}
#   {'loss': '1.925', 'grad_norm': '2.584', 'learning_rate': '0.002707', 'epoch': '1'}
#   {'eval_loss': '1.368', 'eval_accuracy': '0.8178', 'eval_runtime': '0.0353', 'epoch': '1'}
# Only bare numbers were accepted, so a real log from a current version
# produced no metric, no frame and no story.
_HF_DICT_LINE = re.compile(r"^\s*\{['\"]loss['\"].*\}")
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d{1,4})?")

# The dict the Trainer prints once, when training ends:
#   {'train_runtime': '9.366', 'train_samples_per_second': '1438', 'train_loss': '0.5059', ...}
# Its `train_loss` is the average over the whole run, not a reading of the
# last epoch; charted after the last epoch's loss it looks like a jump.
_SUMMARY_KEY = "train_runtime"


def _number(value: object) -> float | None:
    """*value* as a float if it is a number, bare or quoted; else None."""
    # bool is an int in Python: `"should_log": True` is not a reading of 1.0.
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and len(value) <= 40 and _NUMBER.fullmatch(value.strip()):
        return float(value)
    return None


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
        if not isinstance(data, dict):
            return []

        epoch = _number(data.pop("epoch", None))
        if epoch is not None:
            ctx.current_epoch = epoch

        # `step` is training progress, not a metric. Without popping it, the HF
        # parser (which also matches Accelerate's `accelerator.print({...})`
        # dicts) emitted the step count as a bogus `custom` metric on the
        # dashboard and never set the step context.
        step = _number(data.pop("step", None))
        if step is not None:
            ctx.current_step = int(step)

        if _SUMMARY_KEY in data:
            return claim(ctx)

        metrics: list[RawMetric] = []
        for key, val in data.items():
            if key.lower() in NEVER_METRICS:
                continue
            number = _number(val)
            if number is None:
                continue
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    step=ctx.current_step,
                    key=key,
                    value=number,
                    parser_name=self.name,
                    confidence=0.91,
                )
            )
        return metrics
