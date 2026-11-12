"""Train nanoGPT's character-level Shakespeare model on CPU, console output kept.

nanoGPT (github.com/karpathy/nanoGPT) counts iterations, not epochs, and
prints two kinds of line: every `log_interval` iterations the loss of one
batch, and every `eval_interval` iterations an estimate of the training and
the validation loss over `eval_iters` batches each:

    step 250: train loss 2.4293, val loss 2.4447
    iter 260: loss 2.4461, time 16.42ms, mfu 0.08%

    Needs:  pip install torch numpy requests
            nanoGPT/   git clone https://github.com/karpathy/nanoGPT
                       (recorded at commit 3adf61e)
            python nanoGPT/data/shakespeare_char/prepare.py
                       downloads the tiny Shakespeare text (1.1 MB) and
                       writes train.bin, val.bin and meta.pkl beside it
    Run:    python nanogpt_real_source.py > nanogpt_real.log 2>&1

Run from a neutral folder. The settings are the ones nanoGPT's README gives
for a machine without a GPU - a 4-layer model, 64 characters of context -
with its config's own `log_interval`, cut short at 2000 iterations. Nothing
is edited afterwards: the log is train.py's output, byte for byte.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAX_ITERS = sys.argv[1] if len(sys.argv) > 1 else "2000"

ARGS = [
    "config/train_shakespeare_char.py",
    "--device=cpu",
    "--compile=False",
    "--eval_iters=20",
    "--block_size=64",
    "--batch_size=12",
    "--n_layer=4",
    "--n_head=4",
    "--n_embd=128",
    f"--max_iters={MAX_ITERS}",
    f"--lr_decay_iters={MAX_ITERS}",
    "--dropout=0.0",
]


def main() -> None:
    # train.py reads its config and its data relative to the folder it runs in.
    subprocess.run(  # noqa: S603 - nanoGPT's own script, with the arguments above
        [sys.executable, "-u", "train.py", *ARGS], cwd=HERE / "nanoGPT", check=True
    )


if __name__ == "__main__":
    main()
