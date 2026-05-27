from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from epochix.models import RawMetric


@dataclass
class ParserContext:
    """Mutable per-run state handed to every parse_line call."""

    run_id: str
    seq: int = 0
    current_epoch: float | None = None
    current_step: int | None = None
    total_epochs: int | None = None
    extra: dict[str, object] = field(default_factory=dict)


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
