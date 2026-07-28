"""Keys that are never a performance metric, shared by every parser.

Each parser used to keep its own skip list, so a key filtered in one still
leaked through another. `Total params: 462,410` in a Keras model summary was
charted as a flat ``custom`` series worth **462** — the comma truncated it —
on the project's own bundled demo, months after the same class of bug was
fixed in the universal parser.

Import from here rather than redefining a set locally.
"""

from __future__ import annotations

# Totals printed by a model summary. Never a measurement of performance, and
# often mis-parsed anyway because they are comma-grouped.
MODEL_SUMMARY_KEYS = frozenset(
    {
        "params",
        "total_params",
        "trainable_params",
        "non_trainable_params",
        "flops",
        "macs",
    }
)

# Run configuration: constant for the whole run, so charting one draws a flat
# line beside real curves as though the model were doing something.
CONFIG_KEYS = frozenset(
    {
        "batch_size",
        "batchsize",
        "bs",
        "num_workers",
        "workers",
        "img_size",
        "imgsz",
        "epochs",
        "num_epochs",
        "max_epochs",
        "total_epochs",
        "gpus",
        "devices",
        "precision",
        "accumulate_grad_batches",
        "log_every_n_steps",
        "save_top_k",
        "patience",
        "verbose",
        "seed",
        "pid",
        "port",
        "rank",
        "world_size",
        "node",
    }
)

# Units that appear as `key: value` in progress lines ("32ms/step").
UNIT_KEYS = frozenset({"s", "ms", "us", "ns"})

NEVER_METRICS = MODEL_SUMMARY_KEYS | CONFIG_KEYS | UNIT_KEYS
