from __future__ import annotations

# Canonical key → expected unit string (None = dimensionless)
UNIT_MAP: dict[str, str | None] = {
    "accuracy": "%",
    "val_accuracy": "%",
    "precision": "%",
    "recall": "%",
    "f1": "%",
    "mAP": "%",
    "mAP50": "%",
    "TAR": "%",
    "FAR": "%",
    "TAR_at_FAR_0_001": "%",
    "bleu": "%",
    "rouge": "%",
    "EER": "%",
    "MAE": None,      # unit depends on task (degrees or cm)
    "RMSE": None,
    "MSE": None,
    "lr": None,
    "train_loss": None,
    "val_loss": None,
    "box_loss": None,
    "cls_loss": None,
    "dfl_loss": None,
    "perplexity": None,
    "fid": None,
    "is_score": None,
    "epoch_time": "s",
    "eta": "s",
}


def infer_unit(canonical_key: str, value: float) -> str | None:
    """Return the unit string for a canonical key, or None if dimensionless."""
    unit = UNIT_MAP.get(canonical_key)
    # Heuristic: if a 0–1 ratio was reported for a %-metric, treat as already normalised
    if unit == "%" and 0.0 <= value <= 1.0:
        return "%"  # still report %, caller can multiply if needed
    return unit
