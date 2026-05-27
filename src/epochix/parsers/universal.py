from __future__ import annotations

import contextlib
import json
import re

from epochix.models import RawMetric
from epochix.parsers.base import ParserContext
from epochix.parsers.registry import register_parser

# Pattern 1: key=value
_KV_EQ = re.compile(r"(\w+)\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Pattern 2: key: value
_KV_COLON = re.compile(r"(\w+)\s*:\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)")
# Pattern 3: JSON-ish dict anywhere in the line
_JSON_FRAG = re.compile(r"\{[^{}]+\}")

_EPOCH_KEYS = frozenset({"epoch", "ep", "e"})
_STEP_KEYS = frozenset({"step", "iter", "iteration", "batch"})
_SKIP_KEYS = frozenset({"pid", "port", "seed", "rank", "world_size", "node"})


@register_parser
class UniversalParser:
    name = "universal"
    priority = 1  # lowest — always a fallback

    def sniff(self, sample_lines: list[str]) -> float:  # noqa: ARG002
        return 0.10  # always weakly confident; format detector uses this as floor

    def parse_line(self, line: str, ctx: ParserContext) -> list[RawMetric]:  # noqa: C901
        metrics: list[RawMetric] = []
        seen_keys: set[str] = set()

        def add(key: str, val: float, conf: float) -> None:
            key_lo = key.lower()
            if key_lo in seen_keys or key_lo in _SKIP_KEYS:
                return
            seen_keys.add(key_lo)
            if key_lo in _EPOCH_KEYS:
                ctx.current_epoch = val
                return
            if key_lo in _STEP_KEYS:
                ctx.current_step = int(val)
                return
            metrics.append(
                RawMetric(
                    seq=ctx.seq,
                    epoch=ctx.current_epoch,
                    step=ctx.current_step,
                    key=key,
                    value=val,
                    parser_name=self.name,
                    confidence=conf,
                )
            )

        # Pattern 3 first: JSON fragments (highest confidence)
        for frag in _JSON_FRAG.finditer(line):
            text = frag.group().replace("'", '"')
            try:
                obj: dict[str, object] = json.loads(text)
                for k, v in obj.items():
                    if isinstance(v, (int, float)):
                        add(k, float(v), 0.65)
            except json.JSONDecodeError:
                pass

        # Pattern 1: key=value
        for m in _KV_EQ.finditer(line):
            with contextlib.suppress(ValueError):
                add(m.group(1), float(m.group(2)), 0.55)

        # Pattern 2: key: value — lower confidence, more ambiguous
        for m in _KV_COLON.finditer(line):
            with contextlib.suppress(ValueError):
                add(m.group(1), float(m.group(2)), 0.45)

        return metrics
