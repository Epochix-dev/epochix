from __future__ import annotations

import contextlib
import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

# Two shapes of progress line.
#
# What Lightning itself prints (its tqdm bar; epochs count from 0, no total):
#   Epoch 3: 100%|####| 148/148 [00:03<00:00, 38.67it/s, v_num=0, val_loss=1.660, val_acc=0.704]
#
# What a hand-written tqdm loop usually prints, and all this parser used to
# accept — so a real Lightning log matched nothing, and the universal parser
# skips progress bars by design: no metric, no frame, no story.
#   Epoch 3/10: 100%|████| 250/250 [00:12<00:00, loss=0.432, acc=0.867]
_EPOCH_HEADER = re.compile(r"Epoch\s+(\d{1,7})(?:/(\d{1,7})|(?=:))")
_PROGRESS_LINE = re.compile(r"Epoch\s+\d{1,7}(?:/\d{1,7})?:.{0,400}\|")
# "100%|#####| 148/148" — percent, done, total.
_BAR = re.compile(r"(\d{1,3})%\|[^|]{0,400}\|\s*(\d{1,12})/(\d{1,12})")
# The bar's own bracket: "[00:03<00:00, 38.67it/s, val_loss=1.660, ...]".
_POSTFIX = re.compile(r"\|\s*\d{1,12}/\d{1,12}\s*\[([^\]]{0,2000})\]")
_KV_PAIR = re.compile(r"(\w{1,64})\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Lines only Lightning prints. Its preamble (device report, model summary) and
# the validation bars between epochs outnumber the epoch lines, so counting
# epoch lines alone left a real log under the detection threshold.
_LIGHTNING_SIGN = re.compile(
    r"^GPU available: |^LOCAL_RANK: \d|\|\s*Name\s*\|\s*Type\s*\|\s*Params"
    r"|^Validation DataLoader \d|`Trainer\.fit` stopped"
)
_MAX_EPOCHS = re.compile(r"`max_epochs=(\d{1,7})` reached")

# Not metrics: counters, tqdm's rate, the logger's version number, and the
# stopping condition Lightning appends to the last line.
_SKIP_KEYS = frozenset({"epoch", "step", "it", "v_num", "max_epochs", "max_steps"})


@register_parser
class PLParser:
    name = "pytorch_lightning"
    priority = 90

    def sniff(self, sample_lines: list[str]) -> float:
        if any(_LIGHTNING_SIGN.search(line) for line in sample_lines) and any(
            _PROGRESS_LINE.search(line) for line in sample_lines
        ):
            return 0.92
        matches = sum(1 for line in sample_lines if _PROGRESS_LINE.search(line))
        return min(matches / max(len(sample_lines), 1) * 3, 0.95)

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        m = _EPOCH_HEADER.search(line)
        if not m:
            # No epoch header → this is not a training-progress line. Skip
            # metric extraction so config/trailer lines such as
            # "`Trainer.fit` stopped: `max_epochs=30` reached." aren't parsed
            # as bogus 'custom' metrics.
            return []

        printed = int(m.group(1))
        hand_written = m.group(2) is not None
        if hand_written:
            ctx.total_epochs = int(m.group(2))

        bar = _BAR.search(line)
        postfix = _POSTFIX.search(line)
        # Metrics live in the bar's bracket; anything after it is other output
        # that landed on the same line.
        text = postfix.group(1) if postfix else line
        pairs = [
            (kv.group(1), kv.group(2))
            for kv in _KV_PAIR.finditer(text)
            if kv.group(1).lower() not in _SKIP_KEYS
        ]

        if hand_written:
            epoch = float(printed)
        else:
            if bar is not None and bar.group(2) != bar.group(3):
                return claim(ctx)  # a bar caught mid-epoch is not an epoch's result
            # Lightning's bar for epoch N carries the values logged at the end
            # of the epoch before it: validation runs after the bar reaches
            # 100%, and epoch-level training metrics are logged after that. So
            # counted from 0 as printed, "Epoch N" shows epoch N-1's results —
            # which, counted from 1, is simply epoch N. The last epoch has no
            # next bar; Lightning redraws its own line once validation is done,
            # so a second complete "Epoch N" with different values is N+1.
            values = tuple(pairs)
            if ctx.extra.get("pl_printed") == printed:
                if ctx.extra.get("pl_values") == values:
                    return claim(ctx)  # the same line, drawn again
                epoch = float(printed + 1)
            else:
                epoch = float(printed)
            ctx.extra["pl_printed"], ctx.extra["pl_values"] = printed, values
            stopped = _MAX_EPOCHS.search(line)
            if stopped:
                ctx.total_epochs = int(stopped.group(1))
        ctx.current_epoch = epoch

        metrics: list[RawMetric] = []
        for key, val in pairs:
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
