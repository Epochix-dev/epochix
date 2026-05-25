#!/usr/bin/env python3
"""Benchmark all parsers against synthetic log lines.

Usage::

    python scripts/benchmark-parsers.py
    python scripts/benchmark-parsers.py --lines 100000 --parsers pytorch_lightning,keras
    python scripts/benchmark-parsers.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure src/ is on the path when run from the project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from model_story.parsers.registry import detect_parser
from model_story.parsers.base import ParserContext


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
    # Build a combined log to detect from
    sample = lines * 10
    parser = detect_parser(sample)
    if parser is None:
        return {"parser": parser_name, "error": "could not detect"}

    ctx = ParserContext(seq=0, current_epoch=None, total_epochs=None,
                        current_step=None, total_steps=None)
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
        "lines": total_lines,
        "metrics": total_metrics,
        "elapsed_s": round(elapsed, 4),
        "lines_per_sec": int(lps),
        "target_met": lps >= 50_000,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark model-story parsers.")
    ap.add_argument("--lines", type=int, default=50_000,
                    help="Total lines to process per parser (default 50000)")
    ap.add_argument("--parsers", default="all",
                    help="Comma-separated list of parsers, or 'all'")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    args = ap.parse_args()

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
        r = benchmark_parser(name, sample, n)
        results.append(r)
        if not args.json:
            status = "✓" if r.get("target_met") else "✗"
            print(
                f"{status} {r['parser']:25s}  "
                f"{r.get('lines_per_sec', 0):>10,} lines/sec  "
                f"(target ≥ 50,000)"
            )

    if args.json:
        print(json.dumps(results, indent=2))

    failed = [r for r in results if not r.get("target_met")]
    if failed and not args.json:
        print(f"\n{len(failed)} parser(s) below 50k lines/sec target.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
