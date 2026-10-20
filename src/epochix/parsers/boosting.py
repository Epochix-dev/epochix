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
from typing import cast

from epochix.models import RawMetric
from epochix.parsers._never_metrics import NEVER_METRICS, is_setting
from epochix.parsers.base import ParserContext, claim
from epochix.parsers.registry import register_parser

# "[12]" or CatBoost's bare "12:" at the start of the line.
_ROUND = re.compile(r"^\s*(?:\[(\d{1,9})\]|(\d{1,9}):)\s")

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# One "<name>:<value>" pair where the name may carry the separators these
# libraries use and the universal pattern rejects: "-", "'", and a single
# internal space ("valid_0's l2"). Non-greedy so the shortest valid name wins
# rather than swallowing the previous pair's value. A name never starts inside
# a word or a number: CatBoost's timing tail, "total: 137ms<TAB>remaining:
# 8.11s", was read as a metric called "ms<TAB>remaining" on every row.
_PAIR = re.compile(
    rf"(?<![\w.])([A-Za-z][\w'\-]{{0,48}}(?:\s[A-Za-z][\w'\-]{{0,24}})?)\s*:\s*({_NUM})"
)

# CatBoost repeats the running best on every row. It is a derived value, not a
# measurement of this round, and charting it draws a staircase that never
# worsens next to the real curve.
_DERIVED = frozenset({"best", "bestiteration", "best_iteration", "remaining", "total", "elapsed"})

# When training stops, the libraries print the best round once more:
#   Early stopping, best iteration is:                 (LightGBM)
#   Did not meet early stopping. Best iteration is:    (LightGBM)
#   Stopping. Best iteration:                          (XGBoost)
#   [19]	train's l2: 1923.19	valid's l2: 3270.66
# That row is a round already told, not a new measurement. Read as one, a real
# LightGBM run ended its story on a reprint of round 19 after round 29.
_BEST_ITERATION = re.compile(r"best iteration(?: is)?:\s*$", re.IGNORECASE)

# CatBoost's closing summary restates the best round: "bestTest = 0.99266",
# "bestIteration = 50". Both are values already told, not measurements.
_CATBOOST_SUMMARY = re.compile(r"^\s*best(?:Test|Iteration)\s*=", re.IGNORECASE)

# CatBoost names the split and never the metric: "0: test: 0.9790356" is the
# eval metric on the eval set, and nothing on the line says which metric or
# which way it runs. The running best printed beside it does: it follows the
# maximum of an AUC and the minimum of a loss. Until a row shows which, rows
# are held. A metric that has not moved in this many rounds is released under
# a name that claims no direction, so a live run is never held for good.
_CATBOOST_HOLD_ROUNDS = 10
_UNNAMED = ""

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
        # the metric's name nowhere on the line. Naming it after the split
        # ("learn") would chart a metric called learn; what it is called
        # depends on which way it runs, which later rows say (_catboost_name).
        if any(head.startswith(t) for t in _VALIDATION_TOKENS):
            return "val", index, _UNNAMED
        if any(head.startswith(t) for t in _TRAIN_TOKENS):
            return "train", index, _UNNAMED
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


def _catboost_name(test: float | None, best: float | None, last: float | None) -> str | None:
    """What CatBoost's unnamed metric is called, once its direction shows.

    "loss" when its running best follows the minimum, "score" when it follows
    the maximum, ``None`` while a row cannot tell. A row whose value differs
    from its best says so directly. A row equal to its best is a new best, so
    a value that rose to get there is a score and one that fell is a loss.
    """
    if test is None or best is None:
        return None
    if test != best:
        return "score" if best > test else "loss"
    if last is not None and test != last:
        return "score" if test > last else "loss"
    return None


_Row = list[tuple[str | None, int | None, str, float]]


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
            if _BEST_ITERATION.search(line):
                ctx.extra["boosting_reprint_next"] = True
            if _CATBOOST_SUMMARY.match(line):
                return claim(ctx)
            return []
        if ctx.extra.pop("boosting_reprint_next", False):
            return claim(ctx)
        rnd = float(m.group(1) if m.group(1) is not None else m.group(2))
        ctx.current_epoch = rnd
        ctx.current_step = int(rnd)

        body = line[m.end() :]
        found: _Row = []
        best: float | None = None

        for pair in _PAIR.finditer(body):
            raw_name = pair.group(1).strip()
            try:
                value = float(pair.group(2))
            except ValueError:
                continue

            flat = raw_name.replace(" ", "").replace("'", "").replace("-", "").lower()
            if flat == "best":
                # Not charted (a staircase that never worsens), but it is
                # what says which way CatBoost's unnamed metric runs.
                best = value
                continue
            if flat in _DERIVED or raw_name.lower() in NEVER_METRICS:
                continue
            if is_setting(raw_name.lower(), value):
                continue

            split, index, metric = _dissect(raw_name)
            found.append((split, index, metric, value))

        if any(metric == _UNNAMED for _, _, metric, _ in found):
            return self._catboost(found, best, ctx, rnd)
        return self._emit(_resolve_positions(found), ctx.seq, rnd)

    def _catboost(
        self, found: _Row, best: float | None, ctx: ParserContext, rnd: float
    ) -> list[RawMetric]:
        held = cast("list[tuple[int, float, _Row]]", ctx.extra.setdefault("catboost_held", []))
        name = cast("str | None", ctx.extra.get("catboost_name"))
        if name is None:
            if best is None:
                # No eval set: the only split is learn, and it prints the
                # objective being minimised.
                name = "loss"
            else:
                test = next((v for s, _, mt, v in found if s == "val" and mt == _UNNAMED), None)
                last = cast("float | None", ctx.extra.get("catboost_last"))
                name = _catboost_name(test, best, last)
                ctx.extra["catboost_last"] = test
                if name is None and len(held) + 1 < _CATBOOST_HOLD_ROUNDS:
                    held.append((ctx.seq, rnd, found))
                    return claim(ctx)
            ctx.extra["catboost_name"] = name or "metric"
        rows = [*held, (ctx.seq, rnd, found)]
        held.clear()
        told = cast("str", ctx.extra["catboost_name"])
        return [metric for seq, r, row in rows for metric in self._named(row, told, seq, r)]

    def flush(self, ctx: ParserContext) -> list[RawMetric]:
        """Release CatBoost rows still held when the log ends.

        Their metric never moved, so nothing said which way it runs; they are
        told under a name that claims neither.
        """
        held = cast("list[tuple[int, float, _Row]]", ctx.extra.get("catboost_held") or [])
        rows = list(held)
        held.clear()
        return [metric for seq, r, row in rows for metric in self._named(row, "metric", seq, r)]

    def _named(self, found: _Row, name: str, seq: int, rnd: float) -> list[RawMetric]:
        named = [(s, i, name if mt == _UNNAMED else mt, v) for s, i, mt, v in found]
        return self._emit(_resolve_positions(named), seq, rnd)

    def _emit(self, resolved: list[tuple[str, float]], seq: int, rnd: float) -> list[RawMetric]:
        metrics: list[RawMetric] = []
        seen: set[str] = set()
        for key, value in resolved:
            if key in seen:
                continue
            seen.add(key)
            metrics.append(
                RawMetric(
                    seq=seq,
                    epoch=rnd,
                    step=int(rnd),
                    key=key,
                    value=value,
                    parser_name=self.name,
                    confidence=0.80,
                )
            )
        return metrics
