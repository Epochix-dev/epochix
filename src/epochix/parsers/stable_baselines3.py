"""Stable-Baselines3's console table.

At ``verbose=1`` every algorithm prints what its logger recorded as one table
(``HumanOutputFormat``), every rollout for PPO and A2C and every
``log_interval`` episodes for DQN, SAC and TD3. Two recordings
(tests/fixtures/logs/sb3_ppo_real.log, sb3_dqn_real.log) were read as
nothing at all:

    -----------------------------------------
    | rollout/                |             |
    |    ep_len_mean          | 25.8        |
    |    ep_rew_mean          | 25.8        |
    | time/                   |             |
    |    iterations           | 2           |
    |    total_timesteps      | 4096        |
    | train/                  |             |
    |    loss                 | 7.28        |
    -----------------------------------------

A row with no value names a section, and the rows indented under it belong
to it: the value above is ``rollout/ep_rew_mean``, as the library recorded it.
A row neither indented nor empty is a key recorded with no section.

The table is one write (the library joins its lines and flushes once), so it
is read whole: its rows are held until the closing rule and handed over
together. Every line of it is claimed on the way, or the fallback parsers
would read half a table, a row at a time.

What a table counts by. ``time/iterations`` is an on-policy algorithm's
rollout-and-update cycle, and it is not an epoch: PPO runs ``n_epochs`` (10
by default) passes over each rollout, so ``train/n_updates`` reads 10, 20 …
in the recording. Told as an epoch, iteration 7 would be "epoch 7". So a
table with iterations counts by iteration. An off-policy algorithm prints no
iterations, only ``time/episodes`` and ``time/total_timesteps``; its table
counts by step, the environment steps taken. Episodes are not the counter:
the table is printed every few of them, and the steps are what the run was
asked to take (``learn(total_timesteps=…)``).

Not read as metrics: the ``time/`` section (the counters, frames per second
and seconds elapsed) and ``train/n_updates``, a count of gradient updates.
"""

from __future__ import annotations

import contextlib
import math
import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext, claim, count_by
from epochix.parsers.registry import register_parser

# The rule above and below a table: `-` * (key width + value width + 7).
_RULE = re.compile(r"^-{8,400}\s*$")
# "| rollout/    |       |" or "|    ep_rew_mean | 25.8 |": "| ", three spaces
# for a key under a section, the key, " | ", the value, " |".
_ROW = re.compile(r"^\| ( {3})?([^\s|][^|]{0,79}?) *\| ?([^|]{0,80}?) *\|\s*$")
# A section row as the sniff looks for it.
_SECTION = re.compile(r"^\| [a-z][\w-]{0,40}/ *\| *\|\s*$")

_TABLE = "sb3_table"
_SECTION_KEY = "sb3_section"

# Counted, not measured.
_COUNTERS = frozenset({"train/n_updates"})


@register_parser
class StableBaselines3Parser:
    name = "stable_baselines3"
    priority = 82

    def sniff(self, sample_lines: list[str]) -> float:
        sections = sum(1 for line in sample_lines if _SECTION.match(line))
        rules = sum(1 for line in sample_lines if _RULE.match(line))
        return 0.92 if sections >= 2 and rules >= 2 else 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        table = ctx.extra.get(_TABLE)
        if _RULE.match(line):
            if not isinstance(table, dict):
                ctx.extra[_TABLE] = {}
                ctx.extra[_SECTION_KEY] = ""
                return claim(ctx)
            if not table:
                return claim(ctx)  # two rules in a row: still the opening one
            del ctx.extra[_TABLE]
            ctx.extra.pop(_SECTION_KEY, None)
            return self._close(table, ctx) or claim(ctx)

        if not isinstance(table, dict):
            return []
        row = _ROW.match(line)
        if row is None:
            return []
        indented, key, raw = row.group(1), row.group(2), row.group(3)
        if not indented and key.endswith("/") and not raw:
            ctx.extra[_SECTION_KEY] = key
            return claim(ctx)
        section = ctx.extra.get(_SECTION_KEY)
        name = f"{section}{key}" if indented and isinstance(section, str) else key
        # A value that is not a number: nothing to read.
        with contextlib.suppress(ValueError):
            table[name] = float(raw)
        return claim(ctx)

    def _close(self, table: dict[str, float], ctx: ParserContext) -> list[RawMetric]:
        iterations = table.get("time/iterations")
        steps = table.get("time/total_timesteps")
        if steps is not None and math.isfinite(steps):
            ctx.current_step = int(steps)
        if iterations is not None and math.isfinite(iterations):
            count_by(ctx, "iteration", iterations)
        elif steps is not None and math.isfinite(steps):
            count_by(ctx, "step", steps)
        return [
            RawMetric(
                seq=ctx.seq,
                epoch=ctx.current_epoch,
                step=ctx.current_step,
                key=key,
                value=value,
                parser_name=self.name,
                confidence=0.9,
            )
            for key, value in table.items()
            if not key.startswith("time/") and key not in _COUNTERS
        ]
