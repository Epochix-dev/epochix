"""The TensorBoard and W&B importers, against real event data.

Both shipped without ever being executed, and both threw the step away:

* import_tensorboard() produced a run with ZERO frames. EventAccumulator yields
  tag-by-tag (every loss, then every accuracy), the step was discarded, and
  `Loss/train` was mapped to the key `loss_train`, which the normalizer doesn't
  know — so every metric landed as `custom` with epoch=None and the story engine
  emitted nothing at all.
* The W&B importer skipped every `_`-prefixed column, which is where W&B keeps
  the step (`_step`) — so imported runs had no epoch unless the user happened to
  log one explicitly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from epochix.enums import TaskType
from epochix.integrations.tensorboard_import import _tag_to_key
from epochix.integrations.wandb_import import _row_to_metrics
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("Loss/train", "train_loss"),
        ("Accuracy/val", "val_accuracy"),
        ("train/loss", "train_loss"),
        ("validation/accuracy", "val_accuracy"),
        ("eval/loss", "val_loss"),
        ("metrics/mAP50", "map50"),  # YOLO's bare "metrics/" namespace
        ("lr", "lr"),
        ("Loss/test", "test_loss"),
    ],
)
def test_tensorboard_tags_map_to_keys_the_normalizer_knows(tag: str, expected: str) -> None:
    assert _tag_to_key(tag) == expected


def test_tensorboard_import_of_a_real_event_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real SummaryWriter logdir must import as a real run with real epochs."""
    torch_tb = pytest.importorskip("torch.utils.tensorboard")
    pytest.importorskip("tensorboard")

    db = str(tmp_path / "runs.db")
    monkeypatch.setenv("EPOCHIX_DB", db)

    logdir = tmp_path / "tb"
    writer = torch_tb.SummaryWriter(log_dir=str(logdir))
    truth = {}
    for epoch in range(1, 7):
        loss = 2.0 - epoch * 0.25
        acc = 0.45 + epoch * 0.07
        writer.add_scalar("Loss/train", loss, global_step=epoch)
        writer.add_scalar("Accuracy/val", acc, global_step=epoch)
        truth[float(epoch)] = acc
    writer.close()

    from epochix.integrations.tensorboard_import import import_tensorboard

    runs = import_tensorboard(logdir, open_browser=False, run_name="tb-test")
    assert len(runs) == 1, "expected exactly one imported run"
    assert runs[0].id, "import_tensorboard must return Run objects, not id strings"

    store = RunStore(db_path=db)
    frames = store.get_story_frames(runs[0].id)
    metrics = store.get_metric_events(runs[0].id)

    # Regression: this used to be zero.
    assert len(frames) == 6, f"expected 6 frames (one per step), got {len(frames)}"
    assert [f.epoch for f in frames] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

    keys = {m.canonical_key for m in metrics}
    assert keys == {"train_loss", "val_accuracy"}, f"tags did not canonicalize: {keys}"
    assert all(m.epoch is not None for m in metrics), "the TB step was dropped again"

    stored = store.get_run(runs[0].id)
    assert stored is not None
    assert stored.task_type == TaskType.CLASSIFICATION
    assert stored.primary_metric == "val_accuracy"

    # Values must survive the round-trip exactly.
    for m in metrics:
        if m.canonical_key == "val_accuracy":
            assert m.value == pytest.approx(truth[m.epoch], abs=1e-6)


def test_wandb_row_keeps_the_step_as_the_epoch() -> None:
    """W&B hides the step in `_step`; dropping every `_` column dropped it too."""
    pd = pytest.importorskip("pandas")

    history = pd.DataFrame(
        [
            {"_step": 0, "_runtime": 1.2, "train_loss": 2.0, "val_accuracy": 0.41},
            {"_step": 1, "_runtime": 2.4, "train_loss": 1.5, "val_accuracy": 0.62},
        ]
    )
    columns = list(history.columns)

    first = _row_to_metrics(history.iloc[0], columns)
    assert first == {"train_loss": 2.0, "val_accuracy": 0.41, "epoch": 0.0}

    second = _row_to_metrics(history.iloc[1], columns)
    assert second["epoch"] == 1.0
    # W&B bookkeeping must not become a dashboard metric.
    assert "_runtime" not in second


def test_wandb_row_prefers_an_explicit_epoch_and_drops_nan_holes() -> None:
    """Sparse W&B histories are full of NaN; they must not ship as fake values."""
    pd = pytest.importorskip("pandas")

    history = pd.DataFrame(
        [
            {"_step": 50, "epoch": 3.0, "train_loss": 0.9, "val_accuracy": float("nan")},
        ]
    )
    row = _row_to_metrics(history.iloc[0], list(history.columns))

    assert row["epoch"] == 3.0, "an explicit epoch column must win over _step"
    assert "val_accuracy" not in row, "NaN must be dropped, not coerced"
    assert row["train_loss"] == 0.9
