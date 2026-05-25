from __future__ import annotations

import contextlib
import re

from model_story.models import RawMetric
from model_story.parsers.base import ParserContext
from model_story.parsers.registry import register_parser

# FastAI tabular output (variable columns, time at end):
#   0  0.423456  0.312567  0.876543  00:12
_DATA_ROW = re.compile(
    r"^\s*(\d+)\s+"                           # epoch
    r"([\d.eE+-]+)\s+"                        # train_loss
    r"([\d.eE+-]+)\s+"                        # valid_loss
    r"((?:[\d.eE+-]+\s+)*)?"                  # optional extra metrics
    r"(\d{2}:\d{2})\s*$"                      # time
)
# Header detection
_HEADER_LINE = re.compile(r"\btrain_loss\b.*\bvalid_loss\b")


@register_parser
class FastAIParser:
    name = "fastai"
    priority = 75

    def __init__(self) -> None:
        self._extra_headers: list[str] = []

    def sniff(self, sample_lines: list[str]) -> float:
        has_header = any(_HEADER_LINE.search(line) for line in sample_lines)
        has_data = any(_DATA_ROW.match(line) for line in sample_lines)
        if has_header and has_data:
            return 0.90
        if has_header or has_data:
            return 0.40
        return 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        if _HEADER_LINE.search(line):
            # Capture extra metric names beyond train_loss / valid_loss
            parts = line.split()
            self._extra_headers = parts[2:-1] if len(parts) > 3 else []
            return []

        m = _DATA_ROW.match(line)
        if not m:
            return []

        ctx.current_epoch = float(m.group(1))
        train_loss = float(m.group(2))
        valid_loss = float(m.group(3))
        extras_raw = (m.group(4) or "").split()

        metrics: list[RawMetric] = [
            RawMetric(
                seq=ctx.seq,
                epoch=ctx.current_epoch,
                key="train_loss",
                value=train_loss,
                parser_name=self.name,
                confidence=0.88,
            ),
            RawMetric(
                seq=ctx.seq,
                epoch=ctx.current_epoch,
                key="valid_loss",
                value=valid_loss,
                parser_name=self.name,
                confidence=0.88,
            ),
        ]

        for i, val_str in enumerate(extras_raw):
            key = self._extra_headers[i] if i < len(self._extra_headers) else f"metric_{i}"
            with contextlib.suppress(ValueError):
                metrics.append(
                    RawMetric(
                        seq=ctx.seq,
                        epoch=ctx.current_epoch,
                        key=key,
                        value=float(val_str),
                        parser_name=self.name,
                        confidence=0.80,
                    )
                )

        return metrics
