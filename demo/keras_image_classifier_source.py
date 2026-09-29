"""Train a real CNN on real data and print the Keras-style log `epochix demo keras` plays.

scikit-learn's `digits` is 1797 genuine 8x8 handwritten digit images, bundled
with the library, so this needs no download and every number in the log comes
from an actual optimisation — including the timings. The demo it replaced was
hand-written: it skipped epochs 6, 7, 9 … 19 and printed a model summary Keras
cannot produce (a Dense layer straight after a pooling layer, no Flatten).

A small model with a modest learning rate, so the run is still improving at its
last epoch — a different story from the VS Code demo
(epochix-vscode/media/demo_source.py), which is tuned to reach 98 % early.

    python demo/keras_image_classifier_source.py > demo/keras_image_classifier.log
"""

import time

import numpy as np
import torch
import torch.nn as nn
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split

torch.manual_seed(11)
np.random.seed(11)
torch.use_deterministic_algorithms(True)
X, y = load_digits(return_X_y=True)
X = (X / 16.0).astype("float32").reshape(-1, 1, 8, 8)
Xtr, Xva, ytr, yva = train_test_split(X, y, test_size=0.25, random_state=11, stratify=y)
Xtr, Xva = torch.tensor(Xtr), torch.tensor(Xva)
ytr, yva = torch.tensor(ytr), torch.tensor(yva)

model = nn.Sequential(
    nn.Conv2d(1, 16, kernel_size=3, padding=1),
    nn.ReLU(),
    nn.MaxPool2d(2),
    nn.Flatten(),
    nn.Linear(16 * 4 * 4, 32),
    nn.ReLU(),
    nn.Linear(32, 10),
)
EPOCHS, BS = 20, 32
opt = torch.optim.Adam(model.parameters(), lr=0.0005)
lossf = nn.CrossEntropyLoss()

# Keras-style summary with the real per-layer parameter counts.
print('Model: "sequential"')
print("_" * 65)
print(" Layer (type)                Output Shape              Param #")
print("=" * 65)
rows = [
    ("conv2d (Conv2D)", "(None, 16, 8, 8)", model[0]),
    ("max_pooling2d", "(None, 16, 4, 4)", model[2]),
    ("flatten (Flatten)", "(None, 256)", model[3]),
    ("dense (Dense)", "(None, 32)", model[4]),
    ("dense_1 (Dense)", "(None, 10)", model[6]),
]
for label, shape, mod in rows:
    n = sum(p.numel() for p in mod.parameters())
    print(f" {label:<27} {shape:<25} {n}")
print("=" * 65)
total = sum(p.numel() for p in model.parameters())
print(f"Total params: {total:,}")
print(f"Trainable params: {total:,}")
print("Non-trainable params: 0")
print("_" * 65)

n = len(Xtr)
steps = (n + BS - 1) // BS
for epoch in range(1, EPOCHS + 1):
    start = time.perf_counter()
    model.train()
    perm = torch.randperm(n)
    tot, correct = 0.0, 0
    for i in range(0, n, BS):
        idx = perm[i : i + BS]
        opt.zero_grad()
        out = model(Xtr[idx])
        loss = lossf(out, ytr[idx])
        loss.backward()
        opt.step()
        tot += loss.item() * len(idx)
        correct += (out.argmax(1) == ytr[idx]).sum().item()
    tr_loss, tr_acc = tot / n, correct / n
    model.eval()
    with torch.no_grad():
        vo = model(Xva)
        v_loss = lossf(vo, yva).item()
        v_acc = (vo.argmax(1) == yva).float().mean().item()
    elapsed = time.perf_counter() - start
    print(f"Epoch {epoch}/{EPOCHS}")
    print(
        f"{steps}/{steps} [==============================] - {round(elapsed)}s "
        f"{elapsed / steps * 1000:.0f}ms/step - loss: {tr_loss:.4f} - accuracy: {tr_acc:.4f} - "
        f"val_loss: {v_loss:.4f} - val_accuracy: {v_acc:.4f}"
    )
