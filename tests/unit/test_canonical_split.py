"""A held-out metric must stay held-out when its name is canonicalised.

Stripping a `validation_`/`test_` prefix to find the base metric filed
`validation_accuracy` under training `accuracy`, `test_l1` under training
`MAE` and `val_error_rate` under training `error_rate`. The run was then
graded on how well it fit the data it trained on — the one number that keeps
improving while a model overfits. Found by running this engine and the VS
Code extension's side by side over the same names.
"""

from __future__ import annotations

import pytest

from epochix.normalizer.canonical_keys import canonicalize_key


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("validation_accuracy", "val_accuracy"),
        ("validation_f1", "val_f1"),
        ("test_l1", "val_MAE"),
        ("valid_l2", "val_MSE"),
        ("val_mae_cm", "val_MAE"),
        ("eval_rmse_deg", "val_RMSE"),
        ("val_error_rate", "val_error_rate"),
        ("valid_error_rate", "val_error_rate"),
        ("equal_error_rate", "EER"),
    ],
)
def test_a_held_out_prefix_keeps_its_split(raw: str, canonical: str) -> None:
    assert canonicalize_key(raw) == canonical


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("training_accuracy", "accuracy"),
        ("train_mae", "MAE"),
        ("train_l1", "MAE"),
        ("mae_cm", "MAE"),
        # No split exists for these, so any prefix reaches the base metric.
        ("val_precision", "precision"),
        ("test_bleu", "bleu"),
    ],
)
def test_training_and_split_free_metrics_are_unchanged(raw: str, canonical: str) -> None:
    assert canonicalize_key(raw) == canonical


def test_a_validation_only_regression_log_is_graded_on_validation_error() -> None:
    """End to end: a log printing only `validation_mae` and `train_mae`."""
    from datetime import datetime, timezone

    from epochix.models import MetricEvent
    from epochix.story_engine import StoryEngine

    engine = StoryEngine(run_id="split")
    seq = 0
    train = [2.0, 1.4, 1.0, 0.7, 0.5, 0.35]
    val = [2.1, 1.6, 1.3, 1.2, 1.25, 1.35]
    frames = []
    for epoch, (t, v) in enumerate(zip(train, val, strict=True), start=1):
        for raw, value in (("train_mae", t), ("validation_mae", v)):
            event = MetricEvent(
                run_id="split",
                seq=seq,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(epoch),
                canonical_key=canonicalize_key(raw),
                raw_key=raw,
                value=value,
            )
            seq += 1
            frames.extend(engine.process_all(event))
    assert frames
    assert {f.primary_metric for f in frames} == {"val_MAE"}
    assert [f.primary_metric_value for f in frames] == val
