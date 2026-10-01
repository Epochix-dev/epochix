"""A real Hugging Face `Trainer` run, console output kept.

A small MLP on scikit-learn's bundled digits (nothing is downloaded), trained
with `transformers.Trainer` so the log is the Trainer's own: its progress bar
and the dictionaries it prints at each logging and evaluation step.

    Needs:  pip install transformers accelerate torch scikit-learn
    Run:    python huggingface_real_source.py > huggingface_real_trainer.log 2>&1
"""

from __future__ import annotations

import warnings

import numpy as np
import torch
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split
from torch import nn
from transformers import Trainer, TrainingArguments, set_seed

# Python warnings print the path of the file that raised them; a fixture
# carries no machine paths.
warnings.filterwarnings("ignore")


class Digits(torch.utils.data.Dataset):
    def __init__(self, x: np.ndarray, y: np.ndarray) -> None:
        self.x = torch.tensor(x, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i: int) -> dict[str, torch.Tensor]:
        return {"pixel_values": self.x[i], "labels": self.y[i]}


class Classifier(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 10))

    def forward(self, pixel_values: torch.Tensor, labels: torch.Tensor | None = None) -> dict:
        logits = self.net(pixel_values)
        out = {"logits": logits}
        if labels is not None:
            out["loss"] = nn.functional.cross_entropy(logits, labels)
        return out


def accuracy(prediction) -> dict[str, float]:  # noqa: ANN001 - transformers' EvalPrediction
    return {"accuracy": float((prediction.predictions.argmax(-1) == prediction.label_ids).mean())}


def main() -> None:
    set_seed(5)
    digits = load_digits()
    x = digits.data / 16.0
    x_train, x_val, y_train, y_val = train_test_split(
        x, digits.target, test_size=0.25, random_state=5, stratify=digits.target
    )
    args = TrainingArguments(
        output_dir="trainer_output",
        num_train_epochs=10,
        per_device_train_batch_size=32,
        per_device_eval_batch_size=128,
        learning_rate=3e-3,
        eval_strategy="epoch",
        logging_strategy="epoch",
        save_strategy="no",
        report_to="none",
        seed=5,
    )
    trainer = Trainer(
        model=Classifier(),
        args=args,
        train_dataset=Digits(x_train, y_train),
        eval_dataset=Digits(x_val, y_val),
        compute_metrics=accuracy,
    )
    trainer.train()


if __name__ == "__main__":
    main()
