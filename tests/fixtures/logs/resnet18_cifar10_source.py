"""Train ResNet-18 on CIFAR-10 for real, logging plain key=value lines.

Standard recipe: ResNet-18 with the CIFAR stem (3x3 conv, no max-pool), SGD
with Nesterov momentum, one-cycle learning rate, random crop + horizontal
flip, bf16 autocast. The whole dataset sits on the GPU and augmentation runs
there, so no DataLoader workers are needed on Windows.

    python train_resnet18_cifar10.py > resnet18_cifar10.log
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import torchvision
from torch import nn

EPOCHS = 30
BATCH = 256
PEAK_LR = 0.2
WEIGHT_DECAY = 5e-4
SEED = 7
ROOT = Path(__file__).resolve().parent / "data"

MEAN = torch.tensor([0.4914, 0.4822, 0.4465]).view(1, 3, 1, 1)
STD = torch.tensor([0.2470, 0.2435, 0.2616]).view(1, 3, 1, 1)


def load(train: bool, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    ds = torchvision.datasets.CIFAR10(ROOT, train=train, download=True)
    x = torch.from_numpy(np.asarray(ds.data)).permute(0, 3, 1, 2).float().div(255)
    x = ((x - MEAN) / STD).to(device)
    y = torch.tensor(ds.targets, device=device)
    return x, y


def augment(x: torch.Tensor) -> torch.Tensor:
    # Random 32x32 crop from a 4-pixel reflect-padded image, then random flip.
    n = x.shape[0]
    padded = F.pad(x, (4, 4, 4, 4), mode="reflect")
    i = torch.randint(0, 9, (n,), device=x.device)
    j = torch.randint(0, 9, (n,), device=x.device)
    rows = (i.view(n, 1) + torch.arange(32, device=x.device)).view(n, 1, 32, 1)
    cols = (j.view(n, 1) + torch.arange(32, device=x.device)).view(n, 1, 1, 32)
    batch = torch.arange(n, device=x.device).view(n, 1, 1, 1)
    chan = torch.arange(3, device=x.device).view(1, 3, 1, 1)
    out = padded[batch, chan, rows, cols]
    flip = torch.rand(n, device=x.device) < 0.5
    out[flip] = out[flip].flip(3)
    return out


def build_model() -> nn.Module:
    model = torchvision.models.resnet18(num_classes=10)
    model.conv1 = nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1, bias=False)
    model.maxpool = nn.Identity()
    return model


@torch.no_grad()
def evaluate(model: nn.Module, x: torch.Tensor, y: torch.Tensor) -> tuple[float, float]:
    model.eval()
    loss_sum, correct = 0.0, 0
    for k in range(0, x.shape[0], 1000):
        xb = x[k : k + 1000].contiguous(memory_format=torch.channels_last)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = model(xb)
        loss_sum += F.cross_entropy(out.float(), y[k : k + 1000], reduction="sum").item()
        correct += (out.argmax(1) == y[k : k + 1000]).sum().item()
    return loss_sum / x.shape[0], correct / x.shape[0]


def main() -> None:
    torch.manual_seed(SEED)
    device = torch.device("cuda")
    x_train, y_train = load(True, device)
    x_val, y_val = load(False, device)

    model = build_model().to(device, memory_format=torch.channels_last)
    params = sum(p.numel() for p in model.parameters())
    print(f"device: {torch.cuda.get_device_name(0)}  torch {torch.__version__}")
    print(f"dataset: CIFAR-10  train={x_train.shape[0]}  val={x_val.shape[0]}")
    print(model)
    print(f"Total params: {params:,}")
    print(
        f"optimizer: SGD(nesterov, momentum=0.9, weight_decay={WEIGHT_DECAY})  "
        f"schedule: OneCycle(peak_lr={PEAK_LR})  batch={BATCH}  epochs={EPOCHS}"
    )
    sys.stdout.flush()

    opt = torch.optim.SGD(
        model.parameters(), lr=PEAK_LR, momentum=0.9, nesterov=True, weight_decay=WEIGHT_DECAY
    )
    steps = EPOCHS * (x_train.shape[0] // BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=PEAK_LR, total_steps=steps)

    for epoch in range(1, EPOCHS + 1):
        start = time.perf_counter()
        model.train()
        order = torch.randperm(x_train.shape[0], device=device)
        loss_sum, correct, seen = 0.0, 0, 0
        for k in range(0, x_train.shape[0] - BATCH + 1, BATCH):
            idx = order[k : k + BATCH]
            xb = augment(x_train[idx]).contiguous(memory_format=torch.channels_last)
            yb = y_train[idx]
            with torch.autocast("cuda", dtype=torch.bfloat16):
                out = model(xb)
                loss = F.cross_entropy(out.float(), yb)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
            loss_sum += loss.item() * BATCH
            correct += (out.argmax(1) == yb).sum().item()
            seen += BATCH
        val_loss, val_acc = evaluate(model, x_val, y_val)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        print(
            f"Epoch {epoch}/{EPOCHS} train_loss={loss_sum / seen:.4f} "
            f"train_accuracy={correct / seen:.4f} val_loss={val_loss:.4f} "
            f"val_accuracy={val_acc:.4f} lr={opt.param_groups[0]['lr']:.5f} "
            f"epoch_time={elapsed:.1f}s"
        )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
