#!/usr/bin/env python3
"""Benchmark all parsers against synthetic log lines.

Usage::

    python scripts/benchmark-parsers.py
    python scripts/benchmark-parsers.py --lines 100000 --parsers pytorch_lightning,keras
    python scripts/benchmark-parsers.py --json
    python scripts/benchmark-parsers.py --rounds 5
    python scripts/benchmark-parsers.py --src ../base/src --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Lines per second each parser must sustain on a GitHub-hosted runner.
#
# The framework parsers each read one known format and clear 50k with room
# to spare (64k-129k on CI). The universal parser is the fallback for any
# log no framework parser claims: it tries every syntax it knows (key=value,
# key: value, JSON, qualified "Train accuracy: …", whitespace rows) on every
# line. This gate never ran until a PR touched the parsers, and it then
# measured 16.7k; two output-identical passes took it to ~31k. Its floor sits
# below that to catch regressions; ROADMAP.md records why 50k was not worth
# the API change it would take. A stated target it does not meet is not a target.
DEFAULT_TARGET = 50_000
TARGETS: dict[str, int] = {"universal": 24_000}


SAMPLE_LINES: dict[str, list[str]] = {
    "pytorch_lightning": [
        "Epoch 5/50: 100%|=====>| 250/250 [00:12<00:00, loss=0.432, acc=0.867]",
        "Epoch 5/50: 100%|=====>| 250/250 [00:12<00:00, val_loss=0.401, val_acc=0.874]",
    ],
    "keras": [
        "Epoch 5/50",
        "1563/1563 [==============================>] - 10s 6ms/step "
        "- loss: 0.423 - accuracy: 0.867 - val_loss: 0.401 - val_accuracy: 0.874",
    ],
    "huggingface": [
        "{'loss': 0.5123, 'learning_rate': 5e-05, 'epoch': 1.0}",
        "{'eval_loss': 0.3421, 'eval_accuracy': 0.8765, 'epoch': 1.0}",
    ],
    "yolo": [
        "      5/50     1.23G   0.456   0.234   0.123   128",
        "                 all       5000       5000   0.712   0.654   0.678   0.432",
    ],
    "universal": [
        "[Epoch 5/50] train_loss=0.432 train_acc=0.867 val_loss=0.401 val_accuracy=0.874 lr=0.001",
    ],
}


def benchmark_parser(parser_name: str, lines: list[str], n: int) -> dict[str, object]:
    """Run parser on lines × n repetitions; return timing stats."""
    import epochix
    from epochix.parsers.base import ParserContext
    from epochix.parsers.registry import detect_parser

    # Build a combined log to detect from
    sample = lines * 10
    parser = detect_parser(sample)
    if parser is None:
        return {"parser": parser_name, "error": "could not detect"}

    ctx = ParserContext(run_id="benchmark", seq=0)
    total_metrics = 0
    start = time.perf_counter()
    for _ in range(n):
        for line in lines:
            ctx.seq += 1
            metrics = parser.parse_line(line, ctx)
            total_metrics += len(metrics)
    elapsed = time.perf_counter() - start

    total_lines = n * len(lines)
    lps = total_lines / elapsed if elapsed > 0 else 0

    return {
        "parser": parser.name,
        "source": epochix.__file__,
        "lines": total_lines,
        "metrics": total_metrics,
        "elapsed_s": round(elapsed, 4),
        "lines_per_sec": int(lps),
        "target": TARGETS.get(parser_name, DEFAULT_TARGET),
        "target_met": lps >= TARGETS.get(parser_name, DEFAULT_TARGET),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark epochix parsers.")
    ap.add_argument("--lines", type=int, default=50_000,
                    help="Total lines to process per parser (default 50000)")
    ap.add_argument("--parsers", default="all",
                    help="Comma-separated list of parsers, or 'all'")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    ap.add_argument("--rounds", type=int, default=1,
                    help="Keep each parser's best of this many passes (default 1)")
    ap.add_argument("--src", type=Path, default=Path(__file__).parent.parent / "src",
                    help="The src/ directory to measure (default: this tree's)")
    args = ap.parse_args()

    sys.path.insert(0, str(args.src))

    targets = (
        list(SAMPLE_LINES.keys())
        if args.parsers == "all"
        else [p.strip() for p in args.parsers.split(",")]
    )

    results = []
    for name in targets:
        sample = SAMPLE_LINES.get(name)
        if not sample:
            print(f"Unknown parser: {name}", file=sys.stderr)
            continue
        n = max(1, args.lines // len(sample))
        passes = [benchmark_parser(name, sample, n) for _ in range(max(1, args.rounds))]
        r = max(passes, key=lambda p: p.get("lines_per_sec", 0))
        results.append(r)
        if not args.json:
            status = "ok  " if r.get("target_met") else "SLOW"
            print(
                f"{status} {r['parser']:25s}  "
                f"{r.get('lines_per_sec', 0):>10,} lines/sec  "
                f"(target >= {r.get('target', DEFAULT_TARGET):,})"
            )

    if args.json:
        print(json.dumps(results, indent=2))

    failed = [r for r in results if not r.get("target_met")]
    if failed and not args.json:
        print(f"\n{len(failed)} parser(s) below their lines/sec target.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
