#!/usr/bin/env python3
"""Generate a realistic fake training log for any supported framework.

Usage::

    python scripts/generate-fake-log.py --framework pytorch_lightning --epochs 30
    python scripts/generate-fake-log.py --framework keras --epochs 50 --output demo/keras_custom.log
    python scripts/generate-fake-log.py --framework huggingface --task nlp
    python scripts/generate-fake-log.py --list
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path


# ── Curve helpers ─────────────────────────────────────────────────────────────

def _sigmoid(x: float, steepness: float = 6.0) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (x - 0.5)))


def _noisy(val: float, noise: float = 0.008, rng: random.Random = random.Random()) -> float:
    return max(0.0, min(1.0, val + rng.gauss(0, noise)))


def _accuracy_curve(epoch: int, total: int, peak: float = 0.94, rng: random.Random = random.Random()) -> float:
    t = epoch / total
    base = _sigmoid(t) * peak
    return _noisy(base, rng=rng)


def _loss_curve(epoch: int, total: int, start: float = 2.5, floor: float = 0.05, rng: random.Random = random.Random()) -> float:
    t = epoch / total
    base = start * math.exp(-4.0 * t) + floor
    return max(floor, base + rng.gauss(0, 0.02))


# ── Framework formatters ──────────────────────────────────────────────────────

def _pytorch_lightning(epochs: int, rng: random.Random) -> list[str]:
    lines: list[str] = []
    for ep in range(1, epochs + 1):
        n_steps = 250
        loss = _loss_curve(ep, epochs, rng=rng)
        acc = _accuracy_curve(ep, epochs, rng=rng)
        val_loss = _loss_curve(ep, epochs, start=2.3, floor=0.08, rng=rng)
        val_acc = _accuracy_curve(ep, epochs, peak=0.92, rng=rng)
        bar = "=" * 20 + ">"
        lines.append(
            f"Epoch {ep}/{epochs}: 100%|{bar}| {n_steps}/{n_steps} "
            f"[00:{ep * 3 % 60:02d}<00:00, loss={loss:.4f}, acc={acc:.4f}]"
        )
        lines.append(
            f"Epoch {ep}/{epochs}: 100%|{bar}| {n_steps}/{n_steps} "
            f"[00:{ep * 3 % 60:02d}<00:00, val_loss={val_loss:.4f}, val_acc={val_acc:.4f}]"
        )
    return lines


def _keras(epochs: int, rng: random.Random) -> list[str]:
    lines: list[str] = []
    for ep in range(1, epochs + 1):
        lines.append(f"Epoch {ep}/{epochs}")
        steps = 1563
        loss = _loss_curve(ep, epochs, rng=rng)
        acc = _accuracy_curve(ep, epochs, rng=rng)
        val_loss = _loss_curve(ep, epochs, start=2.3, rng=rng)
        val_acc = _accuracy_curve(ep, epochs, peak=0.91, rng=rng)
        elapsed = ep * 8
        lines.append(
            f"{steps}/{steps} [{'=' * 30}>] - {elapsed}s {elapsed * 1000 // steps}ms/step "
            f"- loss: {loss:.4f} - accuracy: {acc:.4f} "
            f"- val_loss: {val_loss:.4f} - val_accuracy: {val_acc:.4f}"
        )
    return lines


def _huggingface(epochs: int, rng: random.Random, task: str = "classification") -> list[str]:
    lines: list[str] = []
    steps_per_epoch = 200
    total_steps = epochs * steps_per_epoch
    for step in range(steps_per_epoch, total_steps + 1, steps_per_epoch):
        ep = step / steps_per_epoch
        loss = _loss_curve(int(ep), epochs, rng=rng)
        lr = 5e-5 * (1 - ep / epochs)
        lines.append(f"{{'loss': {loss:.4f}, 'learning_rate': {lr:.2e}, 'epoch': {ep:.1f}}}")
        eval_loss = _loss_curve(int(ep), epochs, start=2.3, rng=rng)
        if task == "nlp":
            ppl = math.exp(eval_loss * 2)
            lines.append(
                f"{{'eval_loss': {eval_loss:.4f}, 'eval_perplexity': {ppl:.2f}, 'epoch': {ep:.1f}}}"
            )
        else:
            eval_acc = _accuracy_curve(int(ep), epochs, rng=rng)
            lines.append(
                f"{{'eval_loss': {eval_loss:.4f}, 'eval_accuracy': {eval_acc:.4f}, 'epoch': {ep:.1f}}}"
            )
    return lines


def _yolo(epochs: int, rng: random.Random) -> list[str]:
    lines: list[str] = ["YOLOv8 training started"]
    lines.append(
        f"{'':>10}{'Epoch':>7}{'GPU_mem':>11}{'box_loss':>10}{'cls_loss':>10}{'dfl_loss':>10}{'Instances':>11}"
    )
    for ep in range(1, epochs + 1):
        box = _loss_curve(ep, epochs, start=1.2, floor=0.03, rng=rng)
        cls = _loss_curve(ep, epochs, start=1.5, floor=0.04, rng=rng)
        dfl = _loss_curve(ep, epochs, start=0.9, floor=0.02, rng=rng)
        mem = 1.2 + rng.uniform(0, 0.3)
        lines.append(f"      {ep}/{epochs}     {mem:.2f}G   {box:.3f}   {cls:.3f}   {dfl:.3f}   128")
        # Validation row every 5 epochs
        if ep % 5 == 0 or ep == epochs:
            prec = _accuracy_curve(ep, epochs, peak=0.88, rng=rng)
            rec = _accuracy_curve(ep, epochs, peak=0.85, rng=rng)
            map50 = _accuracy_curve(ep, epochs, peak=0.82, rng=rng)
            map95 = map50 * 0.6
            lines.append(
                f"                 all       5000       5000   "
                f"{prec:.3f}   {rec:.3f}   {map50:.3f}   {map95:.3f}"
            )
    return lines


def _universal(epochs: int, rng: random.Random) -> list[str]:
    """Generic key=value format."""
    lines: list[str] = []
    for ep in range(1, epochs + 1):
        loss = _loss_curve(ep, epochs, rng=rng)
        acc = _accuracy_curve(ep, epochs, rng=rng)
        lr = 1e-3 * (0.95 ** ep)
        lines.append(
            f"[Epoch {ep}/{epochs}] train_loss={loss:.4f} train_acc={acc:.4f} "
            f"val_loss={_loss_curve(ep, epochs, start=2.3, rng=rng):.4f} "
            f"val_accuracy={_accuracy_curve(ep, epochs, peak=0.91, rng=rng):.4f} "
            f"lr={lr:.6f}"
        )
    return lines


FRAMEWORKS = {
    "pytorch_lightning": _pytorch_lightning,
    "keras": _keras,
    "huggingface": lambda e, r: _huggingface(e, r),
    "yolo": _yolo,
    "universal": _universal,
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fake training logs.")
    parser.add_argument("--framework", "-f", default="pytorch_lightning",
                        choices=list(FRAMEWORKS), help="Log format to generate")
    parser.add_argument("--epochs", "-e", type=int, default=30,
                        help="Number of epochs (default 30)")
    parser.add_argument("--task", "-t", default="classification",
                        help="Task hint (only used for huggingface)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file (default: stdout)")
    parser.add_argument("--list", action="store_true", help="List supported frameworks")
    args = parser.parse_args()

    if args.list:
        for name in FRAMEWORKS:
            print(f"  {name}")
        return

    rng = random.Random(args.seed)
    gen = FRAMEWORKS[args.framework]

    # Handle extra kwargs for huggingface task
    if args.framework == "huggingface":
        lines = _huggingface(args.epochs, rng, task=args.task)
    else:
        lines = gen(args.epochs, rng)

    text = "\n".join(lines) + "\n"

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Written {len(lines)} lines to {args.output}", file=sys.stderr)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
