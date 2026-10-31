#!/usr/bin/env python3
"""Compare parser throughput between two source trees, on this machine, now.

Numbers from separate CI runs cannot be compared: GitHub's runners come in at
least two speeds, and the same code reads 30k or 45k lines/sec depending on which
it got. So both trees are measured here, by the same script on the same sample
lines, in alternating order so that drift falls on both, and each keeps its best
round, the one least disturbed by whatever else the machine was doing.

Usage::

    git worktree add ../base main
    python scripts/compare_benchmarks.py --base-src ../base/src
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEASURE = REPO / "scripts" / "benchmark-parsers.py"

# How much slower than base a parser may measure before it is called slower.
TOLERANCE = 0.10


def measure(src: Path, lines: int) -> dict[str, dict[str, object]]:
    """One pass over every parser, reading the parsers in `src`."""
    done = subprocess.run(
        [sys.executable, str(MEASURE), "--json", "--lines", str(lines), "--src", str(src)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"Measuring {src} failed:\n{done.stderr}")
    results = json.loads(done.stdout)
    if not results:
        raise SystemExit(f"Measuring {src} returned nothing.")
    for r in results:
        # An editable install must not be measured in place of the tree asked for.
        if not Path(r["source"]).resolve().is_relative_to(src.resolve()):
            raise SystemExit(f"Asked for {src}, measured {r['source']}.")
    return {r["parser"]: r for r in results}


def best_of(src_a: Path, src_b: Path, rounds: int, lines: int) -> tuple[dict, dict]:
    """Best lines/sec per parser for each tree, measured a, b, b, a, a, b, ..."""
    best: tuple[dict, dict] = ({}, {})
    for i in range(rounds):
        order = ((0, src_a), (1, src_b)) if i % 2 == 0 else ((1, src_b), (0, src_a))
        for which, src in order:
            for name, r in measure(src, lines).items():
                kept = best[which].get(name)
                if kept is None or r.get("lines_per_sec", 0) > kept.get("lines_per_sec", 0):
                    best[which][name] = r
    return best


def verdict(base: int | None, head: int | None, target: int | None, tolerance: float) -> str:
    """"ok", or what is wrong. Only a "FAIL" is the change's fault."""
    if head is None:
        return "FAIL: not measured"
    if base is None:
        return "ok: new, nothing to compare with"
    if head < base * (1 - tolerance):
        return f"FAIL: more than {tolerance:.0%} slower than base"
    if target is not None and head < target:
        if base >= target:
            return f"FAIL: below the target of {target:,}"
        # Base misses it too, so this change did not: a slow runner, or main.
        return f"warning: base and head are both below the target of {target:,}"
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare parser throughput with a base tree.")
    ap.add_argument("--base-src", type=Path, required=True, help="The base tree's src/")
    ap.add_argument("--head-src", type=Path, default=REPO / "src", help="Default: this tree's")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--lines", type=int, default=50_000)
    ap.add_argument("--tolerance", type=float, default=TOLERANCE)
    ap.add_argument("--ignore-targets", action="store_true", help="Compare only")
    args = ap.parse_args()

    base, head = best_of(args.base_src, args.head_src, args.rounds, args.lines)

    failed = False
    print(f"{'parser':<20}{'base':>10}{'head':>10}{'change':>9}  verdict")
    for name in sorted(base.keys() | head.keys()):
        b = base.get(name, {}).get("lines_per_sec")
        h = head.get(name, {}).get("lines_per_sec")
        target = None if args.ignore_targets else head.get(name, {}).get("target")
        said = verdict(b, h, target, args.tolerance)
        change = f"{h / b - 1:+.1%}" if b and h else "-"
        print(f"{name:<20}{b or 0:>10,}{h or 0:>10,}{change:>9}  {said}")
        failed = failed or said.startswith("FAIL")
        if said.startswith("warning") and "GITHUB_ACTIONS" in os.environ:
            print(f"::warning::{name}: {said}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
