"""One tqdm bar for the whole run, counting steps.

A LoRA or DreamBooth trainer has no epochs to speak of and prints no line per
step. diffusers' training scripts draw a single bar described "Steps", and
the loss of the last batch rides on it with the learning rate — that bar is
everything the run ever says about how it is going. A recorded run
(tests/fixtures/logs/diffusers_lora_real.log) was told on "Process index: 0":

    Steps:  32%|###2      | 39/120 [00:26<00:43,  1.85it/s, loss=0.0129, lr=0.0001]

The bar is redrawn in place, twice a step: once when the counter moves on,
still carrying the values of the step before, and again when the new values
are set. So a redraw is a reading when its values differ from the last ones
read, and it is told at the step the bar stands at; a redraw that only moved
the counter, or drew the same line again, is claimed. Two steps that print
the same loss and the same learning rate to the last digit are therefore one
reading: nothing on the bar tells them apart.

The redraws of one bar are separated by carriage returns, not newlines, and a
line is otherwise read in its final state. The pipeline hands this bar's
redraws over one at a time (`step_bar_redraws`).

The step is the run's x-axis and the bar's total its length, as a boosting
round is: there is no epoch to count instead.
"""

from __future__ import annotations

import re

from epochix.models import RawMetric
from epochix.parsers._never_metrics import NEVER_METRICS, is_setting
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# 'Steps:  32%|###2      | 39/120 [00:26<00:43,  1.85it/s, loss=0.0129, lr=0.0001]'
# — percent, the bar, done/total, and tqdm's bracket.
_BAR = re.compile(
    r"^\s*steps:\s{1,8}\d{1,3}%\|[^|]{0,400}\|\s*(\d{1,12})/(\d{1,12})\s*\[([^\]]{0,2000})\]",
    re.IGNORECASE,
)
# Cheap to test on every carriage-return segment of every line.
_BAR_START = re.compile(r"^\s*steps:\s{1,8}\d{1,3}%\|", re.IGNORECASE)
_KV_PAIR = re.compile(rf"(?<![\w.])([A-Za-z_]\w{{0,63}})=({_NUM})(?=[,\s]|$)")


def step_bar_redraws(text: str) -> list[str] | None:
    """The redraws of a run-long step bar held in one line, or None.

    *text* is a line as it was written, carriage returns included. Its final
    state comes last, whatever it is, because that is what a line is read as.
    """
    if "\r" not in text:
        return None
    segments = text.split("\r")
    bars = [segment for segment in segments[:-1] if _BAR_START.match(segment)]
    if not bars:
        return None
    return [*bars, segments[-1]]


def finished_step_bar_redraws(partial: str) -> tuple[str | None, str]:
    """The finished redraws of a step bar whose line has not ended yet.

    *partial* is what a live source holds after its last newline. Everything
    before its last carriage return is complete; what follows may be half
    written. Returns the complete redraws as one line (carriage returns
    between them, as `step_bar_redraws` reads them) and what to keep, or
    ``(None, partial)`` when there is no such bar to hand on.
    """
    cut = partial.rfind("\r")
    if cut < 0 or not ("teps:" in partial or "TEPS:" in partial):
        return None, partial
    bars = [segment for segment in partial[:cut].split("\r") if _BAR_START.match(segment)]
    if not bars:
        return None, partial
    return "\r".join(bars), partial[cut + 1 :]


@register_parser
class StepBarParser:
    name = "step_bar"
    priority = 82

    def sniff(self, sample_lines: list[str]) -> float:
        told = 0
        for line in sample_lines:
            bar = _BAR.match(line)
            if bar is not None and _KV_PAIR.search(bar.group(3)):
                told += 1
                if told >= 2:
                    return 0.9
        return 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        bar = _BAR.match(line)
        if bar is None:
            return []
        values = tuple(
            (key, raw)
            for key, raw in _KV_PAIR.findall(bar.group(3))
            if key.lower() not in NEVER_METRICS
        )
        if not values or ctx.extra.get("step_bar_values") == values:
            return claim(ctx)
        ctx.extra["step_bar_values"] = values

        step, total = int(bar.group(1)), int(bar.group(2))
        ctx.current_step = step
        ctx.current_epoch = float(step)
        if total > 0:
            ctx.total_epochs = total

        metrics: list[RawMetric] = []
        for key, raw in values:
            value = float(raw)
            if is_setting(key.lower(), value):
                continue
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    step=ctx.current_step,
                    key=key,
                    value=value,
                    parser_name=self.name,
                    confidence=0.88,
                )
            )
        return metrics or claim(ctx)
