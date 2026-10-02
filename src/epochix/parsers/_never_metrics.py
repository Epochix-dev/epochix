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

# How long something took and how fast it went. The Hugging Face Trainer puts
# these in the same dict as the evaluation metrics, and a real log's
# `eval_samples_per_second` was charted beside its accuracy.
TIMING_KEYS = frozenset(
    {
        "runtime",
        "train_runtime",
        "eval_runtime",
        "test_runtime",
        "samples_per_second",
        "train_samples_per_second",
        "eval_samples_per_second",
        "test_samples_per_second",
        "steps_per_second",
        "train_steps_per_second",
        "eval_steps_per_second",
        "test_steps_per_second",
        "total_flos",
    }
)

NEVER_METRICS = MODEL_SUMMARY_KEYS | CONFIG_KEYS | UNIT_KEYS | TIMING_KEYS

# A name that is a setting or a measurement, and only its value says which.
# `precision` is the numeric precision in a Lightning or AMP log
# (`precision=16`, `precision: 32`) and a classification metric in a training
# loop or a Keras progress bar (`precision: 0.8700`). It was listed as run
# configuration, so the metric was dropped by every parser — a loop printing
# `precision=… recall=…` charted its recall alone. A numeric precision is 16 or
# more; the metric cannot exceed 1.
VALUE_DECIDES = frozenset({"precision"})


def is_setting(key: str, value: float) -> bool:
    """Whether *key* (lower-cased) holding *value* is a setting, not a metric."""
    return key in VALUE_DECIDES and not 0.0 <= value <= 1.0
