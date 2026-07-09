from __future__ import annotations

# Maps raw parser key variants → canonical key name.
# Keys are lowercased before lookup.
CANONICAL_MAP: dict[str, str] = {
    # Loss
    "loss": "train_loss",
    "train_loss": "train_loss",
    "training_loss": "train_loss",
    "trn_loss": "train_loss",
    "val_loss": "val_loss",
    "valid_loss": "val_loss",
    "validation_loss": "val_loss",
    "eval_loss": "val_loss",
    "test_loss": "val_loss",
    # Accuracy
    "acc": "accuracy",
    "accuracy": "accuracy",
    "train_acc": "accuracy",
    "train_accuracy": "accuracy",
    "val_acc": "val_accuracy",
    "val_accuracy": "val_accuracy",
    "valid_accuracy": "val_accuracy",
    "eval_accuracy": "val_accuracy",
    "test_accuracy": "val_accuracy",
    "top1": "accuracy",
    "top_1": "accuracy",
    "top1_accuracy": "accuracy",
    # Learning rate
    "lr": "lr",
    "learning_rate": "lr",
    "lrate": "lr",
    # Detection
    "map": "mAP",
    "map50": "mAP50",
    "map_50": "mAP50",
    "map50-95": "mAP",
    "map_50_95": "mAP",
    "box_loss": "box_loss",
    "cls_loss": "cls_loss",
    "dfl_loss": "dfl_loss",
    "precision": "precision",
    "recall": "recall",
    "f1": "f1",
    "f1_score": "f1",
    # NLP
    "perplexity": "perplexity",
    "ppl": "perplexity",
    "bleu": "bleu",
    "rouge": "rouge",
    "rouge_l": "rouge",
    # Regression / Gaze
    "mae": "MAE",
    "mean_absolute_error": "MAE",
    "rmse": "RMSE",
    "root_mean_squared_error": "RMSE",
    "mse": "MSE",
    # Biometric
    "eer": "EER",
    "tar": "TAR",
    "far": "FAR",
    "tar_at_far_0001": "TAR_at_FAR_0_001",
    "tar_at_far_0.001": "TAR_at_FAR_0_001",
    # Generative
    "fid": "fid",
    "is": "is_score",
    "is_score": "is_score",
    "inception_score": "is_score",
    # Timing
    "epoch_time": "epoch_time",
    "time": "epoch_time",
    "eta": "eta",
}

CANONICAL_SET = frozenset(CANONICAL_MAP.values())

# Split-agnostic metrics have no train/val distinction in CANONICAL_MAP (there
# is one `MAE`, not `train_MAE`/`val_MAE`), so a `val_`/`train_` prefix can be
# stripped to recover the base metric. Metrics that DO split (loss, accuracy)
# list their `val_` forms explicitly above and are matched by direct lookup
# first, so they never reach the stripping logic.
_SPLIT_PREFIXES = (
    "validation_",
    "valid_",
    "training_",
    "eval_",
    "test_",
    "train_",
    "val_",
)

# Unit suffixes frameworks tack onto regression/gaze metrics
# (e.g. mae_cm, val_rmse_deg, mae_mm).
_UNIT_SUFFIXES = ("_cm", "_mm", "_deg", "_rad", "_px", "_percent", "_pct", "_m")


def _strip_units(key: str) -> str:
    for suf in _UNIT_SUFFIXES:
        if key.endswith(suf) and len(key) > len(suf):
            return key[: -len(suf)]
    return key


def canonicalize_key(raw_key: str) -> str:
    """Return the canonical key for a raw parser key, or 'custom' if unknown.

    Matching order:
      1. exact (lower-cased) lookup — handles the explicit val_/train_ forms,
      2. after stripping a known unit suffix (``mae_cm`` → ``mae``),
      3. after stripping a ``val_``/``train_`` prefix and any unit suffix
         (``val_mae_cm`` → ``mae``) — only helps split-agnostic metrics, since
         split metrics were already caught in step 1.
    """
    key = raw_key.lower().strip()

    if key in CANONICAL_MAP:
        return CANONICAL_MAP[key]

    base = _strip_units(key)
    if base in CANONICAL_MAP:
        return CANONICAL_MAP[base]

    for pre in _SPLIT_PREFIXES:
        if key.startswith(pre):
            rest = _strip_units(key[len(pre) :])
            if rest in CANONICAL_MAP:
                return CANONICAL_MAP[rest]
            break

    return "custom"
