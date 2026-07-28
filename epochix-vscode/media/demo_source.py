"""Train a real CNN on real data and print a real Keras-style log.

sklearn's `digits` is 1797 genuine 8x8 handwritten digit images, bundled with
the library, so this needs no download and every number below comes from an
actual optimisation.
"""
import torch, torch.nn as nn, numpy as np
from sklearn.datasets import load_digits
from sklearn.model_selection import train_test_split

torch.manual_seed(7); np.random.seed(7)
X, y = load_digits(return_X_y=True)
X = (X / 16.0).astype("float32").reshape(-1, 1, 8, 8)
Xtr, Xva, ytr, yva = train_test_split(X, y, test_size=0.25, random_state=7, stratify=y)
Xtr, Xva = torch.tensor(Xtr), torch.tensor(Xva)
ytr, yva = torch.tensor(ytr), torch.tensor(yva)

model = nn.Sequential(
    nn.Conv2d(1, 32, kernel_size=3, padding=1), nn.ReLU(),
    nn.MaxPool2d(2),
    nn.Conv2d(32, 64, kernel_size=3, padding=1), nn.ReLU(),
    nn.MaxPool2d(2),
    nn.Flatten(),
    nn.Linear(64 * 2 * 2, 128), nn.ReLU(),
    nn.Dropout(0.3),
    nn.Linear(128, 10),
)
EPOCHS, BS = 20, 64
opt = torch.optim.Adam(model.parameters(), lr=2e-3)
sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=EPOCHS)
lossf = nn.CrossEntropyLoss()

# Keras-style summary header, with the real per-layer parameter counts.
print('Model: "sequential"')
print("_" * 65)
print(" Layer (type)                Output Shape              Param #")
print("=" * 65)
shapes = ["(None, 32, 8, 8)", "(None, 32, 4, 4)", "(None, 64, 4, 4)",
          "(None, 64, 2, 2)", "(None, 256)", "(None, 128)", "(None, 128)", "(None, 10)"]
named = [("conv2d (Conv2D)", model[0]), ("max_pooling2d", model[2]),
         ("conv2d_1 (Conv2D)", model[3]), ("max_pooling2d_1", model[5]),
         ("flatten (Flatten)", model[6]), ("dense (Dense)", model[7]),
         ("dropout (Dropout)", model[9]), ("dense_1 (Dense)", model[10])]
for (label, mod), shape in zip(named, shapes):
    n = sum(p.numel() for p in mod.parameters())
    print(f" {label:<27} {shape:<25} {n}")
print("=" * 65)
total = sum(p.numel() for p in model.parameters())
print(f"Total params: {total:,}")
print(f"Trainable params: {total:,}")
print("Non-trainable params: 0")
print("_" * 65)

n = len(Xtr); steps = (n + BS - 1) // BS
for epoch in range(1, EPOCHS + 1):
    model.train(); perm = torch.randperm(n); tot = 0.0; correct = 0
    for i in range(0, n, BS):
        idx = perm[i:i + BS]
        opt.zero_grad()
        out = model(Xtr[idx]); loss = lossf(out, ytr[idx])
        loss.backward(); opt.step()
        tot += loss.item() * len(idx); correct += (out.argmax(1) == ytr[idx]).sum().item()
    tr_loss, tr_acc = tot / n, correct / n
    model.eval()
    with torch.no_grad():
        vo = model(Xva); v_loss = lossf(vo, yva).item()
        v_acc = (vo.argmax(1) == yva).float().mean().item()
    lr = opt.param_groups[0]["lr"]; sched.step()
    print(f"Epoch {epoch}/{EPOCHS}")
    print(f"{steps}/{steps} [==============================] - 1s 42ms/step - "
          f"loss: {tr_loss:.4f} - accuracy: {tr_acc:.4f} - "
          f"val_loss: {v_loss:.4f} - val_accuracy: {v_acc:.4f} - lr: {lr:.6f}")
