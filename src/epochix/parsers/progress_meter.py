"""The meters of the PyTorch ImageNet example.

`examples/imagenet/main.py` (github.com/pytorch/examples) prints through two
small classes, `AverageMeter` and `ProgressMeter`, that a great deal of
research code copied with it. A recorded run
(tests/fixtures/logs/pytorch_imagenet_real.log) was read as nothing at all:

    Epoch: [0][ 1/32]  Time  0.845 ( 0.845)  Data  0.268 ( 0.268)  Loss 7.1568e+00 (7.1568e+00)
            Acc@1   0.00 (  0.00)  Acc@5   0.00 (  0.00)
    Test: [ 1/10]  Time  0.182 ( 0.182)  Loss 3.7943e+00 (3.7943e+00)  Acc@1   0.00 (  0.00)
            Acc@5  93.75 ( 93.75)
     *   Acc@1 10.333 Acc@5 64.667

(Each row is one line, its columns separated by tabs; wrapped here.)
No pair has a delimiter, the epoch is in brackets after a colon, and `Acc@1`
is not a word. What each line is:

* A training row, every `--print-freq` batches: each meter's value for the
  batch just finished, then its running average over the epoch so far in
  brackets. The loss of the batch is read — the loss at that step — and placed
  at the fraction of the epoch the row itself states: batch 16 of 32 in epoch
  0 is 0.5 epochs in. An ImageNet epoch takes hours, and this is all a run
  says for the first of them.
* A `Test:` row: the same meters part-way through a validation pass. Nothing
  is read from it; the pass's result is the line that follows.
* ` * Acc@1 … Acc@5 …`: the validation result for the epoch just trained. It
  carries no epoch of its own, so it is told at the number of epochs finished.

The training rows' `Acc@1` is one batch's accuracy, and told row by row it
became the story: seven frames of "accuracy 12.5%", graded F, before the first
validation result replaced them with a different series. What a row does say
about the epoch is the running average in its brackets, so the last row's is
kept and told with the validation result it belongs beside — one training
accuracy per epoch, on the line that carries the validation accuracy.

`Acc@k` is a percentage by construction (`correct_k.mul_(100.0 / batch_size)`),
so it is divided by 100 here. Left to the normalizer, which takes a value of 1
or less for a fraction, a batch that got one image in 256 right (`Acc@1 0.39`)
would be told as 39% — and that is every early batch of a real ImageNet run.

The training rows' `Acc@5` is not read: there is one top-5 series, and the
validation result is the one that says how the model is doing. Nor are `Time`
and `Data`, which time a batch and its loading.
"""

from __future__ import annotations

import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# "Epoch: [0][ 1/32]" — the epoch counted from 0, the batch, the batches.
_TRAIN_ROW = re.compile(r"^Epoch: \[(\d{1,7})\]\[\s*(\d{1,9})/\s*(\d{1,9})\]\s")
_TEST_ROW = re.compile(r"^Test: {0,2}\[\s*\d{1,9}/\s*\d{1,9}\]\s")
_SUMMARY = re.compile(r"^ \*\s")
# "Loss 7.0228e+00 (7.0228e+00)" — a meter: name, value, (running average).
_METER = re.compile(rf"(?<=\s)([A-Za-z][\w@]{{0,31}})\s+({_NUM})\s+\(\s*({_NUM})\)")
# "Acc@1 11.000" on the summary line — a meter's average alone.
_AVERAGE = re.compile(rf"(?<=\s)([A-Za-z][\w@]{{0,31}})\s+({_NUM})(?=\s|$)")
_ACC_AT = re.compile(r"^acc@(\d{1,3})$", re.IGNORECASE)

# How long a batch took and how long its data took to load.
_TIMERS = frozenset({"time", "data"})


def _top_k(name: str) -> str | None:
    """The k of a top-k accuracy meter (`Acc@5` -> "5"), or None."""
    top = _ACC_AT.match(name)
    return top.group(1) if top is not None else None


def _value(name: str, raw: str) -> float:
    if _top_k(name) is None:
        return float(raw)
    # "75.667" as 0.75667: read with the exponent rather than divided, which
    # gives 0.7566700000000001.
    return float(raw) / 100.0 if "e" in raw.lower() else float(f"{raw}e-2")


@register_parser
class ProgressMeterParser:
    name = "progress_meter"
    priority = 80

    def sniff(self, sample_lines: list[str]) -> float:
        rows = sum(1 for line in sample_lines if _TRAIN_ROW.match(line) or _TEST_ROW.match(line))
        return 0.9 if rows >= 2 else 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        row = _TRAIN_ROW.match(line)
        if row is not None:
            epoch, batch, batches = int(row.group(1)), int(row.group(2)), int(row.group(3))
            ctx.extra["meter_epoch"] = epoch
            if batches > 0:
                ctx.current_epoch = epoch + batch / batches
                ctx.current_step = epoch * batches + batch
            readings: list[tuple[str, float]] = []
            for name, raw, average in _METER.findall(line):
                if name.lower() in _TIMERS:
                    continue
                top = _top_k(name)
                if top is None:
                    readings.append((name, float(raw)))
                elif top == "1":
                    # The epoch so far; told with the validation result.
                    ctx.extra["meter_train_accuracy"] = (name, _value(name, average))
            return self._metrics(readings, ctx) or claim(ctx)

        if _TEST_ROW.match(line):
            return claim(ctx)  # a validation pass caught part-way through

        if _SUMMARY.match(line):
            trained = ctx.extra.get("meter_epoch")
            if isinstance(trained, int):
                ctx.current_epoch = float(trained + 1)
            readings = [
                (f"val_{name}", _value(name, raw))
                for name, raw in _AVERAGE.findall(line)
                if name.lower() not in _TIMERS
            ]
            kept = ctx.extra.pop("meter_train_accuracy", None)
            if readings and isinstance(kept, tuple):
                readings.append(kept)
            return self._metrics(readings, ctx) or claim(ctx)

        return []

    def _metrics(self, readings: list[tuple[str, float]], ctx: ParserContext) -> list[RawMetric]:
        return [
            RawMetric(
                seq=ctx.seq,
                epoch=ctx.current_epoch,
                step=ctx.current_step,
                key=key,
                value=value,
                parser_name=self.name,
                confidence=0.88,
            )
            for key, value in readings
        ]
