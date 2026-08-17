"""Gradient boosting: XGBoost, LightGBM, CatBoost.

These print one row per boosting round, prefixed with the round in brackets:

    [0]	validation_0-logloss:0.51987	validation_1-logloss:0.52369   (XGBoost)
    [2]	valid_0's l2: 30497.7                                        (LightGBM)
    0:	learn: 0.6798710	test: 0.6801448	best: 0.6801448 (0)          (CatBoost)

The universal parser could not read them. Its key pattern is ``\\w{1,64}``,
which stops at the ``-`` in ``validation_0-logloss`` and at the space in
``valid_0's l2``, so every eval set on the line collapsed to the same key
(``logloss``, ``l2``) — and because the universal parser keeps only the first
occurrence of a key, the *second* eval set was silently dropped. A run with a
training and a validation curve charted one line and called it the whole story,
which is the opposite of what a boosting log is worth reading for: the gap
between those two curves IS the overfitting signal.

The round number is the x-axis. It is not an epoch in the neural-network sense,
but it is the same thing structurally — one more unit of fitting — and the
story engine already reasons about progress along that axis.
"""

from __future__ import annotations

import re

from epochix.models import RawMetric
from epochix.parsers._never_metrics import NEVER_METRICS
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import register_parser

# "[12]" or CatBoost's bare "12:" at the start of the line.
_ROUND = re.compile(r"^\s*(?:\[(\d{1,9})\]|(\d{1,9}):)\s")

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# One "<name>:<value>" pair where the name may carry the separators these
# libraries use and the universal pattern rejects: "-", "'", and a single
# internal space ("valid_0's l2"). Non-greedy so the shortest valid name wins
# rather than swallowing the previous pair's value.
_PAIR = re.compile(rf"([A-Za-z][\w'\-]{{0,48}}(?:\s[A-Za-z][\w'\-]{{0,24}})?)\s*:\s*({_NUM})")

# CatBoost repeats the running best on every row. It is a derived value, not a
# measurement of this round, and charting it draws a staircase that never
# worsens next to the real curve.
_DERIVED = frozenset({"best", "bestiteration", "best_iteration", "remaining", "total", "elapsed"})

# How each library names the split. Order matters: "validation" must be tested
# before "valid", and "training" before "train".
_VALIDATION_TOKENS = ("validation", "valid", "eval", "test", "holdout", "dev")
_TRAIN_TOKENS = ("training", "train", "learn", "fit")


def _dissect(name: str) -> tuple[str | None, int | None, str]:
    """Break "validation_0-logloss" into ("val", 0, "logloss").

    The middle element is the eval set's position, which XGBoost's sklearn API
    uses instead of a name. ``(None, None, name)`` when there is no split
    qualifier, so a bare "rmse" stays bare rather than being assigned a split
    it never claimed.
    """
    # "valid_0's l2" → "valid_0 l2" → parts ["valid", "0", "l2"]
    cleaned = name.replace("'s", " ").replace("-", " ").replace("\t", " ")
    parts = [p for p in re.split(r"[\s_]+", cleaned.strip()) if p]
    if not parts:
        return None, None, name

    head = parts[0].lower()
    index = next((int(p) for p in parts[1:] if p.isdigit()), None)
    rest = [p for p in parts[1:] if not p.isdigit()]

    if not rest:
        # CatBoost writes the split alone — "learn: 0.679  test: 0.680" — with
        # the objective's name nowhere on the line. The number is that
        # objective's value on that split, so it is a loss; naming it after the
        # split ("learn") would chart it as a metric called learn.
        if any(head.startswith(t) for t in _VALIDATION_TOKENS):
            return "val", index, "loss"
        if any(head.startswith(t) for t in _TRAIN_TOKENS):
            return "train", index, "loss"
        return None, None, name

    metric = "_".join(rest).lower()
    if any(head.startswith(t) for t in _VALIDATION_TOKENS):
        return "val", index, metric
    if any(head.startswith(t) for t in _TRAIN_TOKENS):
        return "train", index, metric
    return None, None, name


def _resolve_positions(
    found: list[tuple[str | None, int | None, str, float]],
) -> list[tuple[str, float]]:
    """Turn positional eval sets into train/validation, per metric.

    XGBoost's sklearn API names eval sets by position — ``validation_0``,
    ``validation_1`` — and says nothing about which is which. Mapping both to
    "val" made them one key, so the second was dropped and the run charted a
    single curve; that is the collapse this parser exists to undo.

    ``eval_set=[(X_train, y_train), (X_test, y_test)]`` is the ordering in
    XGBoost's own documentation and in practically every tutorial, so where
    several indexed sets appear on one row the earliest is read as training and
    the last as validation. A single set is left as validation, which is what
    one eval set is nearly always for (early stopping).

    The inference only applies to positional names. ``valid_0``, ``learn`` and
    ``test`` say what they are, and are taken at their word. The original name
    is preserved on the metric's raw_key either way, so the dashboard can
    always show what the library actually printed.
    """
    by_metric: dict[str, list[tuple[int | None, float]]] = {}
    out: list[tuple[str, float]] = []

    for split, index, metric, value in found:
        if split == "val" and index is not None:
            by_metric.setdefault(metric, []).append((index, value))
        elif split:
            out.append((f"{split}_{metric}", value))
        else:
            out.append((metric, value))

    for metric, entries in by_metric.items():
        if len(entries) == 1:
            out.append((f"val_{metric}", entries[0][1]))
            continue
        ordered = sorted(entries, key=lambda e: e[0] if e[0] is not None else 0)
        out.append((f"train_{metric}", ordered[0][1]))
        out.append((f"val_{metric}", ordered[-1][1]))
        # Three or more eval sets: keep the middle ones rather than discard
        # them, named by the position the library gave them.
        for idx, value in ordered[1:-1]:
            out.append((f"eval{idx}_{metric}", value))

    return out


@register_parser
class BoostingParser:
    """XGBoost / LightGBM / CatBoost round-by-round evaluation rows."""

    name = "boosting"
    # Above universal, below the framework-specific neural parsers: a Lightning
    # log never looks like this, and this must not be shadowed by the fallback.
    priority = 6

    def sniff(self, sample_lines: list[str]) -> float:
        rows = 0
        for line in sample_lines:
            if _ROUND.match(line) and _PAIR.search(line):
                rows += 1
        if rows >= 3:
            return 0.85
        if rows >= 1:
            return 0.40
        return 0.0

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        m = _ROUND.match(line)
        if m is None:
            return []
        rnd = float(m.group(1) if m.group(1) is not None else m.group(2))
        ctx.current_epoch = rnd
        ctx.current_step = int(rnd)

        body = line[m.end() :]
        found: list[tuple[str | None, int | None, str, float]] = []

        for pair in _PAIR.finditer(body):
            raw_name = pair.group(1).strip()
            try:
                value = float(pair.group(2))
            except ValueError:
                continue

            flat = raw_name.replace(" ", "").replace("'", "").replace("-", "").lower()
            if flat in _DERIVED or raw_name.lower() in NEVER_METRICS:
                continue

            split, index, metric = _dissect(raw_name)
            found.append((split, index, metric, value))

        return self._emit(_resolve_positions(found), ctx, rnd)

    def _emit(
        self,
        resolved: list[tuple[str, float]],
        ctx: ParserContext,
        rnd: float,
    ) -> list[RawMetric]:
        metrics: list[RawMetric] = []
        seen: set[str] = set()
        for key, value in resolved:
            if key in seen:
                continue
            seen.add(key)
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=rnd,
                    step=int(rnd),
                    key=key,
                    value=value,
                    parser_name=self.name,
                    confidence=0.80,
                )
            )
        return metrics
