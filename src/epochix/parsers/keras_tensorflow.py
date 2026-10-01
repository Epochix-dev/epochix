from __future__ import annotations

import contextlib
import re

from epochix.models import RawMetric
from epochix.parsers._never_metrics import NEVER_METRICS
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

# Epoch header: "Epoch 1/50"
_EPOCH_LINE = re.compile(r"^Epoch\s+(\d+)/(\d+)\s*$")
# A progress line, in each layout Keras has printed:
#   1563/1563 [==============================] - 10s 6ms/step - loss: 0.423 ...   (Keras 2)
#   43/43 ━━━━━━━━━━━━━━━━━━━━ 0s 6ms/step - accuracy: 0.9473 - loss: 0.2216 ...   (Keras 3)
#   43/43 - 0s - 5ms/step - accuracy: 0.9473 - loss: 0.2216 ...                    (verbose=2)
# Step counts are bounded ({1,10}) so an unanchored search can't backtrack O(n²)
# on a long digit run (a 200k-digit line froze the sniff for ~12s).
_METRIC_LINE = re.compile(r"\d{1,10}/\d{1,10}\s+(?:\[=+>?\.*\]|━{2,}|-\s+\d{1,6}s\s+-)")
# The step counter that opens a progress line: done/total.
_STEPS = re.compile(r"^\s*(\d{1,10})/(\d{1,10})\s")
# Keras prints every metric as " - name: value" (Keras 2 and 3 alike), so the
# dash is required. Without it any "word: number" on any line was a metric:
# "Dataset | Train: 4200 | Val: 800" charted the dataset sizes, "Total params:
# 462,410" a parameter count, and a tqdm "[00:12<00:00" a metric named `00`.
_KV_PAIR = re.compile(r"(?:^|\s)-\s+([A-Za-z_]\w{0,63}):\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")

# Shared so a key filtered in one parser cannot leak through another.
_SKIP_KEYS = NEVER_METRICS


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

        # A bar caught mid-epoch is not the epoch's result. Written to a file,
        # Keras 3 puts every progress update on its own line — "12/43 ━━━ ...
        # accuracy: 0.1172" — and each was read as a reading: a real run's
        # first epoch became five frames of running training accuracy.
        steps = _STEPS.match(line)
        if steps is not None and steps.group(1) != steps.group(2):
            return claim(ctx)

        # With validation data Keras 3 prints the finished bar twice — once
        # when training ends and again with the validation metrics added. The
        # values it repeats are one measurement, not two.
        told = ctx.extra.get("keras_told")
        if not isinstance(told, dict) or ctx.extra.get("keras_told_epoch") != ctx.current_epoch:
            told = {}
            ctx.extra["keras_told"] = told
            ctx.extra["keras_told_epoch"] = ctx.current_epoch

        metrics: list[RawMetric] = []
        for kv in _KV_PAIR.finditer(line):
            key, val = kv.group(1), kv.group(2)
            if key.lower() in _SKIP_KEYS:
                continue
            if told.get(key) == val:
                continue
            told[key] = val
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
        if steps is not None and not metrics:
            return claim(ctx)  # a finished bar that only repeated itself
        return metrics
