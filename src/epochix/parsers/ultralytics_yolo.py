from __future__ import annotations

import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

# Training row: "      1/50     1.23G   0.456   0.234   0.123   128"
_TRAIN_ROW = re.compile(
    r"^\s*(\d+)/(\d+)\s+"  # epoch/total
    r"[\d.]+[GMK]?\s+"  # GPU mem
    r"([\d.]+)\s+"  # box_loss
    r"([\d.]+)\s+"  # cls_loss
    r"([\d.]+)\s+"  # dfl_loss
    r"\d+"  # instances
)

# Validation row: "all   5000   5000   0.712   0.654   0.678   0.432"
_VAL_ROW = re.compile(
    r"^\s*all\s+"
    r"\d+\s+\d+\s+"
    r"([\d.]+)\s+"  # precision
    r"([\d.]+)\s+"  # recall
    r"([\d.]+)\s+"  # mAP50
    r"([\d.]+)"  # mAP50-95
)


# After the last epoch Ultralytics validates the best checkpoint once more:
#   Validating runs\detect\train\weights\best.pt...
#                    all        128        929      0.808      0.732      0.814      0.638
# That row is a second measurement of an epoch already told, not another
# epoch. Read as one, a 3-epoch run was told "after 4 epochs", and a 30-epoch
# run ended on "a change of -0.2 points since the previous reading".
_FINAL_VALIDATION = re.compile(r"^Validating\s.{1,400}\.pt\b")


@register_parser
class YOLOParser:
    name = "ultralytics_yolo"
    priority = 88

    def sniff(self, sample_lines: list[str]) -> float:
        train_hits = sum(1 for line in sample_lines if _TRAIN_ROW.match(line))
        val_hits = sum(1 for line in sample_lines if _VAL_ROW.match(line))
        score = (train_hits + val_hits * 2) / max(len(sample_lines), 1)
        return min(score * 4, 0.94)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        m = _TRAIN_ROW.match(line)
        if m:
            ctx.current_epoch = float(m.group(1))
            ctx.total_epochs = int(m.group(2))
            return [
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="box_loss",
                    value=float(m.group(3)),
                    parser_name=self.name,
                    confidence=0.92,
                ),
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="cls_loss",
                    value=float(m.group(4)),
                    parser_name=self.name,
                    confidence=0.92,
                ),
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="dfl_loss",
                    value=float(m.group(5)),
                    parser_name=self.name,
                    confidence=0.92,
                ),
            ]

        if _FINAL_VALIDATION.match(line):
            ctx.extra["yolo_final_validation"] = True
            return []

        m = _VAL_ROW.match(line)
        if m and ctx.extra.get("yolo_final_validation"):
            return claim(ctx)
        if m:
            return [
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="precision",
                    value=float(m.group(1)),
                    parser_name=self.name,
                    confidence=0.93,
                ),
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="recall",
                    value=float(m.group(2)),
                    parser_name=self.name,
                    confidence=0.93,
                ),
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="mAP50",
                    value=float(m.group(3)),
                    parser_name=self.name,
                    confidence=0.93,
                ),
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    key="mAP",
                    value=float(m.group(4)),
                    parser_name=self.name,
                    confidence=0.93,
                ),
            ]

        return []
