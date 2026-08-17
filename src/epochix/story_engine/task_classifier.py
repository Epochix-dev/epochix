from __future__ import annotations

import re

from epochix.enums import TaskType

# Names that say the model predicts where someone is looking. Nothing else
# distinguishes gaze from any other regression — see refine_gaze.
_GAZE_HINT = re.compile(r"gaze|angular|pitch|yaw|eye_|_eye\b|fixation", re.IGNORECASE)

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
        # The val_ forms matter for gradient boosting, which prints its
        # validation error and often nothing else: without them an XGBoost
        # regression run classified as CUSTOM and was graded on trajectory.
        frozenset(
            {
                "MAE",
                "RMSE",
                "MSE",
                "R2",
                "MAPE",
                "MedAE",
                "RMSLE",
                "explained_variance",
                "val_MAE",
                "val_RMSE",
                "val_MSE",
                "val_R2",
                "val_MAPE",
            }
        ),
        TaskType.REGRESSION,
    ),  # any error metric → regression / gaze
    (
        frozenset(
            {
                "accuracy",
                "val_accuracy",
                "AUC",
                "val_AUC",
                "PR_AUC",
                "top5_accuracy",
                "balanced_accuracy",
                "MCC",
                "kappa",
                "error_rate",
                "val_error_rate",
                "log_loss",
                "val_log_loss",
            }
        ),
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


def refine_gaze(task: TaskType, mae_value: float, seen_keys: set[str] | None = None) -> TaskType:
    """Promote REGRESSION → GAZE, but only on an actual gaze signal.

    This used to promote any regression whose MAE was below 10, on the theory
    that gaze error is measured in single-digit degrees. So is most regression:
    a Ridge model on ordinary data reported MAE 9.83 and was narrated as *"the
    model sees the face but not the gaze"*, with the value printed in degrees.
    The task, the story and the unit were all invented from one number's
    magnitude.

    A metric's size cannot tell you what the model predicts. The name can, so
    that is what is required now — the magnitude is only a secondary check,
    since a genuine gaze run reporting MAE 340 is not measuring degrees.
    """
    if task != TaskType.REGRESSION or mae_value >= 10.0:
        return task
    if any(_GAZE_HINT.search(key) for key in (seen_keys or set())):
        return TaskType.GAZE
    return task
