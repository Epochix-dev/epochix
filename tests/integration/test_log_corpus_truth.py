"""Every log in the repository, through the real pipeline, against what it contains.

Two fixtures here (ansi_colors.log, mixed_frameworks.log) were never read by
any test, and both came out wrong. Driving the whole corpus found more:

* garbage.log — a web server's log — got a training story: "Response sent: 200"
  and "keys: 0.234" were filed under one name, "custom", and narrated as a
  model "past its best, 200.0 -> 0.234", graded F.
* fingerprint_matching.log, a headline demo, told 50 epochs as ONE reading: the
  Keras parser won detection on its "Epoch 15/50" lines and could not read the
  `train_loss=... EER=...` lines under them. It also charted the dataset sizes
  ("Train: 4200 | Val: 800").
* Every Keras / Lightning run's first frame was TRAINING accuracy and the rest
  validation accuracy — one chart, two series, and the baseline from the wrong
  one; a one-epoch run was graded on training accuracy.
* A tqdm "[00:12<00:00" became a metric named `00`; an orphaned colour code a
  metric named `1mloss`.

The expectations were reviewed against the files, not copied from a run: the
frame count is the number of epochs that print the story's metric, the value is
the last one the log prints, and the key set is exactly the metrics it reports.
A log added to demo/ or tests/fixtures/logs without an entry here fails.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

ROOT = Path(__file__).resolve().parents[2]
LOGS = {
    **{p.name: p for p in (ROOT / "demo").glob("*.log")},
    **{p.name: p for p in (ROOT / "tests" / "fixtures" / "logs").glob("*.log")},
    "vscode-demo.log": ROOT / "epochix-vscode" / "media" / "demo.log",
}

# name: (task, primary metric, frames, last value, every metric key stored)
TRUTH: dict[str, tuple[str, str | None, int, float | None, tuple[str, ...]]] = {
    "fingerprint_matching.log": (
        "biometric",
        "EER",
        13,
        0.0212,
        ("EER", "TAR_at_FAR_0_001", "lr", "train_loss"),
    ),
    "gaze_estimation.log": ("regression", "MAE", 18, 1.587, ("MAE", "lr", "train_loss")),
    "huggingface_bert.log": (
        "classification",
        "val_accuracy",
        10,
        0.8456,
        ("lr", "train_loss", "val_accuracy", "val_f1", "val_loss"),
    ),
    "keras_image_classifier.log": (
        "classification",
        "val_accuracy",
        11,
        0.7834,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "pytorch_lightning.log": (
        "classification",
        "val_accuracy",
        14,
        0.876,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "seq2seq_attention.log": (
        "classification",
        "val_accuracy",
        8,
        0.771,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "yolov8_detection.log": (
        "detection",
        "mAP50",
        11,
        0.663,
        ("box_loss", "cls_loss", "dfl_loss", "mAP", "mAP50", "precision", "recall"),
    ),
    "accelerate_real.log": (
        "classification",
        "val_accuracy",
        4,
        0.86,
        ("train_loss", "val_accuracy", "val_loss"),
    ),
    "ansi_colors.log": ("classification", "accuracy", 3, 0.632, ("accuracy", "train_loss")),
    "detection_coco.log": (
        "detection",
        "mAP50",
        10,
        0.741,
        ("box_loss", "cls_loss", "dfl_loss", "mAP", "mAP50", "precision", "recall"),
    ),
    "diverging_loss.log": (
        "classification",
        "val_accuracy",
        5,
        0.589,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "empty.log": ("custom", None, 0, None, ()),
    "fastai_real.log": (
        "classification",
        "accuracy",
        4,
        0.8594,
        ("accuracy", "train_loss", "val_loss"),
    ),
    "garbage.log": ("custom", None, 0, None, ()),
    "hf_classification.log": (
        "classification",
        "val_accuracy",
        20,
        0.8964,
        ("lr", "train_loss", "val_accuracy", "val_loss"),
    ),
    "huggingface_5ep.log": (
        "classification",
        "val_accuracy",
        5,
        0.8895,
        ("lr", "train_loss", "val_accuracy", "val_loss"),
    ),
    "huggingface_nlp_10ep.log": (
        "nlp",
        "perplexity",
        10,
        1.18,
        ("lr", "perplexity", "train_loss", "val_loss"),
    ),
    "interrupted.log": ("classification", "val_accuracy", 3, 0.521, ("train_loss", "val_accuracy")),
    "keras_100ep.log": (
        "classification",
        "val_accuracy",
        100,
        0.853,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "keras_50ep.log": (
        "classification",
        "val_accuracy",
        50,
        0.8668,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "keras_short.log": (
        "classification",
        "val_accuracy",
        10,
        0.8564,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "mixed_frameworks.log": (
        "classification",
        "val_accuracy",
        4,
        0.801,
        ("accuracy", "lr", "train_loss", "val_accuracy", "val_loss"),
    ),
    "multiline_json.log": (
        "classification",
        "val_accuracy",
        5,
        0.6789,
        ("lr", "train_loss", "val_accuracy", "val_f1", "val_loss"),
    ),
    "no_val_metrics.log": ("classification", "accuracy", 5, 0.689, ("accuracy", "train_loss")),
    "pl_high_accuracy.log": (
        "classification",
        "val_accuracy",
        20,
        0.8728,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "plateau.log": ("classification", "val_accuracy", 10, 0.825, ("train_loss", "val_accuracy")),
    "pytorch_lightning_30ep.log": (
        "classification",
        "val_accuracy",
        30,
        0.8735,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "pytorch_lightning_long.log": (
        "classification",
        "val_accuracy",
        100,
        0.8818,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "pytorch_lightning_short.log": (
        "classification",
        "val_accuracy",
        5,
        0.8752,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "scientific_notation.log": ("custom", "val_loss", 5, 0.28, ("lr", "train_loss", "val_loss")),
    "single_epoch.log": (
        "classification",
        "val_accuracy",
        1,
        0.874,
        ("accuracy", "train_loss", "val_accuracy", "val_loss"),
    ),
    "universal_20ep.log": (
        "classification",
        "val_accuracy",
        20,
        0.8728,
        ("accuracy", "lr", "train_loss", "val_accuracy", "val_loss"),
    ),
    "universal_kv_colon.log": (
        "classification",
        "val_accuracy",
        30,
        0.8527,
        ("accuracy", "lr", "train_loss", "val_accuracy", "val_loss"),
    ),
    "yolo_100ep.log": (
        "detection",
        "mAP50",
        25,
        0.783,
        ("box_loss", "cls_loss", "dfl_loss", "mAP", "mAP50", "precision", "recall"),
    ),
    "yolo_50ep.log": (
        "detection",
        "mAP50",
        15,
        0.798,
        ("box_loss", "cls_loss", "dfl_loss", "mAP", "mAP50", "precision", "recall"),
    ),
    "yolo_real_ultralytics.log": (
        "detection",
        "mAP50",
        5,
        0.688,
        ("box_loss", "cls_loss", "dfl_loss", "mAP", "mAP50", "precision", "recall"),
    ),
    "yolo_short.log": (
        "detection",
        "mAP50",
        7,
        0.781,
        ("box_loss", "cls_loss", "dfl_loss", "mAP", "mAP50", "precision", "recall"),
    ),
    "vscode-demo.log": (
        "classification",
        "val_accuracy",
        20,
        0.98,
        ("accuracy", "lr", "train_loss", "val_accuracy", "val_loss"),
    ),
}


def test_every_log_has_an_expectation() -> None:
    assert len(LOGS) >= 38, "the corpus went missing"
    assert set(LOGS) == set(TRUTH)


def _run(path: Path) -> tuple[str, str | None, int, float | None, tuple[str, ...]]:
    store = RunStore(":memory:")
    run = asyncio.run(
        run_pipeline(ingester=FileBatchIngester("c", str(path)), run_id="c", store=store, hub=Hub())
    )
    frames = store.get_story_frames("c")
    events = store.get_metric_events("c")
    last = frames[-1] if frames else None
    return (
        run.task_type.value if run.task_type else "custom",
        last.primary_metric if last else None,
        len(frames),
        round(last.primary_metric_value, 4) if last else None,
        tuple(sorted({e.canonical_key for e in events})),
    )


@pytest.mark.parametrize("name", sorted(TRUTH))
def test_the_log_tells_what_it_contains(name: str) -> None:
    task, metric, frames, last_value, keys = _run(LOGS[name])
    want_task, want_metric, want_frames, want_value, want_keys = TRUTH[name]
    assert keys == want_keys, f"metrics stored: {keys}"
    assert (task, metric) == (want_task, want_metric)
    assert frames == want_frames
    assert last_value == want_value


def test_one_story_metric_per_run() -> None:
    """The first frame is not a different series from the rest."""
    for name in ("pytorch_lightning_30ep.log", "keras_short.log", "pl_high_accuracy.log"):
        store = RunStore(":memory:")
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("s", str(LOGS[name])), run_id="s", store=store, hub=Hub()
            )
        )
        assert {f.primary_metric for f in store.get_story_frames("s")} == {"val_accuracy"}, name
