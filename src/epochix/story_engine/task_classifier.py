from __future__ import annotations

from epochix.enums import TaskType

# Keys that strongly imply a task type
_TASK_SIGNALS: list[tuple[frozenset[str], TaskType]] = [
    (frozenset({"EER", "TAR", "FAR", "TAR_at_FAR_0_001"}), TaskType.BIOMETRIC),
    # Segmentation before detection: a segmentation run often logs mAP-style
    # keys too, but IoU/Dice are the decisive signal for what it actually is.
    (frozenset({"mIoU", "IoU", "Dice", "pixel_accuracy"}), TaskType.SEGMENTATION),
    (frozenset({"mAP", "mAP50", "box_loss", "cls_loss"}), TaskType.DETECTION),
    (frozenset({"perplexity", "bleu", "rouge", "WER", "CER", "BPC"}), TaskType.NLP),
    # Image quality metrics: a restoration/generation run, not a classifier.
    (frozenset({"PSNR", "SSIM", "LPIPS"}), TaskType.GENERATIVE),
    (frozenset({"fid", "is_score"}), TaskType.GENERATIVE),
    (
        frozenset({"MAE", "RMSE", "MSE", "R2", "MAPE"}),
        TaskType.REGRESSION,
    ),  # any error metric → regression / gaze
    (
        frozenset({"accuracy", "val_accuracy", "AUC", "PR_AUC", "top5_accuracy"}),
        TaskType.CLASSIFICATION,
    ),
]


def classify_task(seen_keys: set[str]) -> TaskType:
    """Infer task type from the set of canonical keys observed so far.

    Called once ≥3 metric events have been collected. Checks signal sets in
    priority order; first match wins. Falls back to CUSTOM.
    """
    for signal_set, task in _TASK_SIGNALS:
        if signal_set & seen_keys:
            return task
    return TaskType.CUSTOM


def refine_gaze(task: TaskType, mae_value: float) -> TaskType:
    """Promote REGRESSION → GAZE when MAE is suspiciously small (< 10 degrees/cm)."""
    if task == TaskType.REGRESSION and mae_value < 10.0:
        return TaskType.GAZE
    return task
