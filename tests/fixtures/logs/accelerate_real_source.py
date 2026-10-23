"""A small loop run through Hugging Face Accelerate, console output kept.

`accelerator.print` of a dict at the end of each epoch, carrying the global
`step` as well as the epoch — the shape the 0.5.16 capture had, whose `step`
the parser once stored as a metric of its own.

    Needs:  pip install accelerate torch scikit-learn
    Run:    python accelerate_real_source.py > accelerate_real.log 2>&1

Run from a neutral folder. scikit-learn's bundled digits, a small MLP, CPU.
"""

from __future__ import annotations

import warnings

import torch
from accelerate import Accelerator
from accelerate.utils import set_seed
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

# Python warnings print the path of the file that raised them.
warnings.filterwarnings("ignore")

set_seed(3)
x, y = load_digits(return_X_y=True)
xt, xv, yt, yv = train_test_split(x / 16.0, y, test_size=0.25, random_state=3)


def loader(features: object, labels: object, shuffle: bool) -> DataLoader[tuple[torch.Tensor, ...]]:
    data = TensorDataset(
        torch.tensor(features, dtype=torch.float32), torch.tensor(labels, dtype=torch.long)
    )
    return DataLoader(data, batch_size=135, shuffle=shuffle)


accelerator = Accelerator(cpu=True)
model = nn.Sequential(nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 10))
optimiser = torch.optim.SGD(model.parameters(), lr=0.1)
model, optimiser, train, valid = accelerator.prepare(
    model, optimiser, loader(xt, yt, True), loader(xv, yv, False)
)
criterion = nn.CrossEntropyLoss()

step = 0
for epoch in range(4):
    model.train()
    total = 0.0
    seen = 0
    for features, labels in train:
        optimiser.zero_grad()
        loss = criterion(model(features), labels)
        accelerator.backward(loss)
        optimiser.step()
        step += 1
        total += loss.item() * len(labels)
        seen += len(labels)

    model.eval()
    val_total = 0.0
    correct = val_seen = 0
    with torch.no_grad():
        for features, labels in valid:
            out = model(features)
            val_total += criterion(out, labels).item() * len(labels)
            correct += (out.argmax(1) == labels).sum().item()
            val_seen += len(labels)

    accelerator.print(
        {
            "loss": round(total / seen, 4),
            "val_loss": round(val_total / val_seen, 4),
            "val_accuracy": round(correct / val_seen, 4),
            "step": step,
            "epoch": epoch,
        }
    )
