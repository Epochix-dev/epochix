"""The Lightning / HuggingFace StoryCallbacks, driven by the REAL frameworks.

docs/quickstart.md leads with these two callbacks, but they were only ever
exercised duck-typed — and all three of the bugs below shipped as a result:

* Lightning invokes hooks via bare ``getattr(cb, hook)``, so a callback that
  didn't subclass ``pl.Callback`` crashed ``trainer.fit()`` on ``setup`` before
  epoch 1 — the integration was 100% broken.
* The HF callback WAS rebound to a TrainerCallback subclass, but with the bases
  the wrong way round (``class StoryCallback(TrainerCallback, StoryCallback)``),
  so HF's no-op hooks shadowed ours: training ran clean and stored nothing.
* The HF callback defaulted primary_metric to "eval_loss", so a classifier at
  84% accuracy was graded on its loss and came out F.

They need the real frameworks installed (see the `integrations` CI job); they
skip otherwise so the default suite stays light.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest

from epochix.enums import TaskType
from epochix.store.sqlite_store import RunStore

if TYPE_CHECKING:
    from pathlib import Path

torch = pytest.importorskip("torch")

EPOCHS = 4


def _blobs(n: int, seed: int) -> Any:
    """Three overlapping gaussian blobs — genuinely learnable, never trivial."""
    from torch.utils.data import TensorDataset

    g = torch.Generator().manual_seed(seed)
    centers = torch.tensor([[-2.0, -2.0], [2.0, -2.0], [0.0, 2.5]])
    y = torch.randint(0, 3, (n,), generator=g)
    x = centers[y] + 1.8 * torch.randn(n, 2, generator=g)
    return TensorDataset(x, y)


def _net() -> Any:
    from torch import nn

    return nn.Sequential(nn.Linear(2, 32), nn.ReLU(), nn.Linear(32, 3))


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "runs.db")
    monkeypatch.setenv("EPOCHIX_DB", path)
    return path


def _only_run(db_path: str) -> Any:
    store = RunStore(db_path=db_path)
    runs = store.list_runs()
    assert len(runs) == 1, f"expected exactly one stored run, got {len(runs)}"
    run = runs[0]
    return run, store.get_story_frames(run.id), store.get_metric_events(run.id)


def _import_lightning() -> Any:
    """Whichever Lightning is installed.

    `pip install epochix[lightning]` pulls the LEGACY `pytorch-lightning`
    distribution, whose Callback is a different class object from the modern
    `lightning` package's. Importorskip-ing only `lightning.pytorch` made this
    test skip silently on exactly the version we promise to support.
    """
    import importlib

    for name in ("lightning.pytorch", "pytorch_lightning"):
        try:
            return importlib.import_module(name)
        except ImportError:
            continue
    pytest.skip("neither lightning nor pytorch_lightning is installed")


def test_lightning_callback_drives_a_real_trainer(db: str) -> None:
    pl = _import_lightning()
    from torch.nn import functional as F  # noqa: N812
    from torch.utils.data import DataLoader

    from epochix.integrations.lightning import StoryCallback

    class Classifier(pl.LightningModule):
        def __init__(self) -> None:
            super().__init__()
            self.net = _net()

        def training_step(self, batch: Any, _: int) -> Any:
            x, y = batch
            loss = F.cross_entropy(self.net(x), y)
            self.log("train_loss", loss, on_epoch=True, on_step=False)
            return loss

        def validation_step(self, batch: Any, _: int) -> None:
            x, y = batch
            logits = self.net(x)
            self.log("val_loss", F.cross_entropy(logits, y), on_epoch=True)
            self.log("val_accuracy", (logits.argmax(1) == y).float().mean(), on_epoch=True)

        def configure_optimizers(self) -> Any:
            return torch.optim.SGD(self.parameters(), lr=0.01)

    trainer = pl.Trainer(
        max_epochs=EPOCHS,
        callbacks=[StoryCallback(task="classification", name="pl-test", open_browser=False)],
        accelerator="cpu",
        logger=False,
        enable_checkpointing=False,
        enable_model_summary=False,
        enable_progress_bar=False,
    )
    # Regression: this used to raise AttributeError('setup') before epoch 1.
    trainer.fit(
        Classifier(),
        DataLoader(_blobs(400, 0), batch_size=64),
        DataLoader(_blobs(200, 1), batch_size=64),
    )

    run, frames, metrics = _only_run(db)
    assert run.task_type == TaskType.CLASSIFICATION
    assert run.primary_metric == "val_accuracy", (
        f"a classification run must be graded on accuracy, not {run.primary_metric}"
    )

    # One frame per epoch — the validation hook used to re-log every val metric
    # that on_train_epoch_end already sent, doubling frames and events.
    assert len(frames) == EPOCHS, f"expected {EPOCHS} frames, got {len(frames)}"
    assert [f.epoch for f in frames] == [float(i) for i in range(EPOCHS)]

    for key in ("val_accuracy", "val_loss", "train_loss"):
        n = sum(1 for m in metrics if m.canonical_key == key)
        assert n == EPOCHS, f"{key}: expected {EPOCHS} events, got {n} (duplicated?)"

    # Every metric belongs to a real epoch. The duplicate val events used to
    # land with epoch=None because the hook filtered on `"val" in key`, which
    # dropped the epoch key itself.
    assert all(m.epoch is not None for m in metrics)


def test_hf_callback_drives_a_real_trainer(db: str) -> None:
    pytest.importorskip("transformers")
    pytest.importorskip("accelerate")
    import numpy as np
    from torch import nn
    from torch.utils.data import Dataset
    from transformers import Trainer, TrainingArguments

    from epochix.integrations.hf import StoryCallback

    class Blobs(Dataset):  # type: ignore[type-arg]
        def __init__(self, n: int, seed: int) -> None:
            ds = _blobs(n, seed)
            self.x, self.y = ds.tensors

        def __len__(self) -> int:
            return len(self.y)

        def __getitem__(self, i: int) -> dict[str, Any]:
            return {"x": self.x[i], "labels": self.y[i]}

    class TinyClassifier(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.net = _net()

        def forward(self, x: Any = None, labels: Any = None) -> dict[str, Any]:
            logits = self.net(x)
            loss = nn.functional.cross_entropy(logits, labels) if labels is not None else None
            return {"loss": loss, "logits": logits}

    def collate(features: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "x": torch.stack([f["x"] for f in features]),
            "labels": torch.stack([f["labels"] for f in features]),
        }

    def compute_metrics(pred: Any) -> dict[str, float]:
        logits, labels = pred
        return {"accuracy": float((np.argmax(logits, axis=1) == labels).mean())}

    common = {
        "output_dir": os.path.join(os.path.dirname(db), "hf_out"),
        "num_train_epochs": EPOCHS,
        "per_device_train_batch_size": 64,
        "per_device_eval_batch_size": 64,
        "logging_strategy": "epoch",
        "save_strategy": "no",
        "learning_rate": 0.05,
        "report_to": [],
        "disable_tqdm": True,
        "use_cpu": True,
    }
    try:
        args = TrainingArguments(eval_strategy="epoch", **common)
    except TypeError:
        # transformers < 5 spells it `evaluation_strategy`. The callback itself
        # doesn't care, but the declared floor (4.40) is a supported version and
        # this test has to run there.
        args = TrainingArguments(evaluation_strategy="epoch", **common)
    Trainer(
        model=TinyClassifier(),
        args=args,
        train_dataset=Blobs(400, 0),
        eval_dataset=Blobs(200, 1),
        data_collator=collate,
        compute_metrics=compute_metrics,
        callbacks=[StoryCallback(task="classification", name="hf-test", open_browser=False)],
    ).train()

    # Regression: the inverted MRO made every hook a no-op, so NOTHING was
    # stored — training looked perfectly healthy and the dashboard stayed empty.
    run, frames, metrics = _only_run(db)
    assert run.task_type == TaskType.CLASSIFICATION
    assert run.primary_metric == "val_accuracy", (
        f"a classifier must be graded on accuracy, not {run.primary_metric} "
        "(defaulting primary_metric to eval_loss graded an 84%-accurate model F)"
    )
    assert len(frames) == EPOCHS, f"expected {EPOCHS} frames, got {len(frames)}"

    accs = [m.value for m in metrics if m.canonical_key == "val_accuracy"]
    assert len(accs) == EPOCHS
    assert all(0.0 <= a <= 1.0 for a in accs)

    # HF's throughput bookkeeping must not pollute the dashboard as metrics.
    raw_keys = [m.raw_key.lower() for m in metrics]
    assert not any("samples_per_second" in k for k in raw_keys), raw_keys
    assert not any("steps_per_second" in k for k in raw_keys), raw_keys
    assert not any(k.endswith("_runtime") for k in raw_keys), raw_keys
