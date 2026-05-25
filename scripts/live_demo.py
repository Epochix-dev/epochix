"""Live training simulator — streams a mock ResNet training run to the server.

Simulates 20 epochs of image-classification training with realistic loss/accuracy
curves.  Each epoch is sent with a 1.5-second pause so you can watch the grade
and narrative update live in the browser.

Usage
-----
    python scripts/live_demo.py [--port 7860] [--epochs 20] [--delay 1.5]
"""
from __future__ import annotations

import argparse
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import json


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def simulate(*, base: str, epochs: int, delay: float) -> None:
    # ── Create the run ────────────────────────────────────────────────────────
    run = _post(
        f"{base}/api/runs",
        {
            "name": "ResNet-50 live demo",
            "task": "classification",
            "primary_metric": "val_accuracy",
            "total_epochs": epochs,
        },
    )
    run_id = run["id"]
    print(f"\n  Run ID : {run_id}")
    print(f"  Dashboard: {base}/v/{run_id}\n")

    # Open the browser automatically
    import webbrowser
    webbrowser.open(f"{base}/v/{run_id}")
    time.sleep(1.5)  # let the browser load first

    seq = 0

    for epoch in range(1, epochs + 1):
        progress = epoch / epochs
        # Smooth loss curves with noise
        noise = (math.sin(epoch * 2.7) * 0.01)
        train_loss  = 1.2 * math.exp(-3.5 * progress) + 0.08 + noise
        val_loss    = 1.3 * math.exp(-3.0 * progress) + 0.12 + noise * 0.5
        train_acc   = 1 - math.exp(-4.0 * progress) * 0.85 + noise * 0.5
        val_acc     = 1 - math.exp(-3.5 * progress) * 0.88 + noise * 0.3
        # Clamp
        train_acc = max(0.0, min(1.0, train_acc))
        val_acc   = max(0.0, min(1.0, val_acc))

        metrics = [
            ("train_loss",   "train_loss",   train_loss),
            ("val_loss",     "val_loss",     val_loss),
            ("accuracy",     "train_acc",    train_acc),
            ("val_accuracy", "val_acc",      val_acc),
        ]

        for canonical_key, raw_key, value in metrics:
            _post(
                f"{base}/api/runs/{run_id}/event",
                {
                    "seq":           seq,
                    "epoch":         float(epoch),
                    "canonical_key": canonical_key,
                    "raw_key":       raw_key,
                    "value":         round(value, 4),
                },
            )
            seq += 1

        # Fetch the latest frame (if any) and print it
        try:
            snap = _get(f"{base}/api/snapshot/{run_id}")
            frames = snap.get("frames", [])
            if frames:
                f = frames[-1]
                bar_len = 20
                filled = int(progress * bar_len)
                bar = "#" * filled + "-" * (bar_len - filled)
                grade = f["grade"]
                phase = f["phase"]
                narrative_preview = f["narrative"][:72]
                sys.stdout.write(
                    f"  Epoch {epoch:2d}/{epochs}  [{bar}]  "
                    f"{phase:12s}  {grade}  val_acc={val_acc:.3f}\n"
                )
                sys.stdout.write(f"            {narrative_preview}...\n")
                sys.stdout.flush()
            else:
                sys.stdout.write(
                    f"  Epoch {epoch:2d}/{epochs}  (collecting metrics...)"
                    f"  val_acc={val_acc:.3f}\n"
                )
                sys.stdout.flush()
        except Exception as exc:
            sys.stdout.write(
                f"  Epoch {epoch:2d}/{epochs}  val_acc={val_acc:.3f}"
                f"  val_loss={val_loss:.3f}  [{type(exc).__name__}: {exc}]\n"
            )
            sys.stdout.flush()

        time.sleep(delay)

    print(f"\n  Training complete!  Final val_accuracy: {val_acc:.3f}")
    print(f"  Dashboard: {base}/v/{run_id}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="model-story live training demo")
    parser.add_argument("--port",   type=int,   default=7860)
    parser.add_argument("--epochs", type=int,   default=20)
    parser.add_argument("--delay",  type=float, default=1.5,
                        help="seconds between epochs (default 1.5)")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"

    # Quick health check
    try:
        _get(f"{base}/api/health")
    except Exception:
        print(f"ERROR: Server not reachable at {base}", file=sys.stderr)
        sys.exit(1)

    simulate(base=base, epochs=args.epochs, delay=args.delay)
