from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, cast, runtime_checkable

from epochix.models import Counter, RawMetric


@dataclass
class ParserContext:
    """Mutable per-run state handed to every parse_line call."""

    run_id: str
    seq: int = 0
    current_epoch: float | None = None
    current_step: int | None = None
    total_epochs: int | None = None
    extra: dict[str, object] = field(default_factory=dict)


# Set in ``ctx.extra`` by a parser that recognises a line as its own and reads
# no result from it; the pipeline then does not offer the line to the fallback
# parsers. Cleared after every line.
LINE_CLAIMED = "line_claimed"


def claim(ctx: ParserContext) -> list[RawMetric]:
    """Mark the current line as recognised-but-empty; returns no metrics."""
    ctx.extra[LINE_CLAIMED] = True
    return []


# Set in ``ctx.extra`` by a parser that puts something other than an epoch in
# ``current_epoch`` — a boosting round, an iteration, a step — naming what it
# is. Cleared after every line, as LINE_CLAIMED is: it says what THIS line
# counted by, so the kind always belongs to whoever wrote the number last.
COUNTED_BY = "counted_by"


def count_by(ctx: ParserContext, counter: Counter, value: float) -> None:
    """Put *value* in the epoch slot and say what it counts."""
    ctx.current_epoch = value
    ctx.extra[COUNTED_BY] = counter


def counter_after(ctx: ParserContext, before: float | None, current: Counter) -> Counter:
    """What the epoch slot counts once a line has been read.

    *before* is the slot as it stood before the line and *current* what it
    counted then. A parser that wrote a round or a step said so (`count_by`);
    one that moved the slot and said nothing wrote an epoch; a line that left
    the slot alone changes nothing.
    """
    said = cast("Counter | None", ctx.extra.pop(COUNTED_BY, None))
    if said is not None:
        return said
    return "epoch" if ctx.current_epoch != before else current


@runtime_checkable
class BaseParser(Protocol):
    """Protocol every parser must satisfy."""

    name: str
    priority: int

    def sniff(self, sample_lines: list[str]) -> float:
        """Return confidence 0.0–1.0 that this parser owns the format.

        Called on the first 50 lines (or 5 s of live data). Must be fast and
        stateless — it may be called multiple times with different samples.
        """
        ...

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:
        """Parse a single line and return zero or more RawMetric objects."""
        ...
