"""A hand-written PyTorch training loop with tqdm bars, console output kept.

The shape the Lightning-named format samples imitate (pytorch_lightning_30ep.log
and its siblings): one bar over the training batches and one over the
validation batches per epoch, each described "Epoch N/M" and carrying its
running numbers through set_postfix. Lightning itself prints neither.

    python tqdm_loop_real_source.py > tqdm_loop_real.log 2>&1

Run from a neutral folder. scikit-learn's bundled digits, a small MLP, CPU.
"""

from __future__ import annotations

import torch
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

torch.manual_seed(3)
x, y = load_digits(return_X_y=True)
xt, xv, yt, yv = train_test_split(x / 16.0, y, test_size=0.25, random_state=3)


def loader(features: object, labels: object, shuffle: bool) -> DataLoader[tuple[torch.Tensor, ...]]:
    data = TensorDataset(
        torch.tensor(features, dtype=torch.float32), torch.tensor(labels, dtype=torch.long)
    )
    return DataLoader(data, batch_size=32, shuffle=shuffle)


train, valid = loader(xt, yt, True), loader(xv, yv, False)
model = nn.Sequential(nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 10))
optimiser = torch.optim.SGD(model.parameters(), lr=0.05)
criterion = nn.CrossEntropyLoss()
epochs = 12

for epoch in range(1, epochs + 1):
    model.train()
    seen = correct = 0
    total = 0.0
    bar = tqdm(train, desc=f"Epoch {epoch}/{epochs}")
    for features, labels in bar:
        optimiser.zero_grad()
        out = model(features)
        loss = criterion(out, labels)
        loss.backward()
        optimiser.step()
        seen += len(labels)
        total += loss.item() * len(labels)
        correct += (out.argmax(1) == labels).sum().item()
        bar.set_postfix(loss=f"{total / seen:.4f}", acc=f"{correct / seen:.4f}")

    model.eval()
    seen = correct = 0
    total = 0.0
    bar = tqdm(valid, desc=f"Epoch {epoch}/{epochs}")
    with torch.no_grad():
        for features, labels in bar:
            out = model(features)
            seen += len(labels)
            total += criterion(out, labels).item() * len(labels)
            correct += (out.argmax(1) == labels).sum().item()
            bar.set_postfix(val_loss=f"{total / seen:.4f}", val_acc=f"{correct / seen:.4f}")
