"""Run the PyTorch ImageNet example on a tiny image folder, console output kept.

`examples/imagenet/main.py` (github.com/pytorch/examples) is the script whose
meters half the research code on GitHub copied: a row every `--print-freq`
batches, each value followed by its running average in brackets, tab
separated, and one summary line after each validation pass:

    Epoch: [0][ 1/32]	Time  0.845 ( 0.845)	Data  0.268 ( 0.268)	Loss 7.1568e+00 (7.1568e+00)	Acc@1   0.00 (  0.00)	Acc@5   0.00 (  0.00)
    Test: [ 1/10]	Time  0.182 ( 0.182)	Loss 3.7943e+00 (3.7943e+00)	Acc@1   0.00 (  0.00)	Acc@5  93.75 ( 93.75)
     *   Acc@1 10.333 Acc@5 64.667

    Needs:  pip install torch torchvision scikit-learn pillow
            examples/   git clone https://github.com/pytorch/examples
                        (recorded at commit acc295d)
    Run:    python pytorch_imagenet_real_source.py > pytorch_imagenet_real.log 2>&1

Run from a neutral folder. The image folder is scikit-learn's bundled
handwritten digits written out as PNG files, one folder per class: 100 of
each digit to train on and 30 to validate on. ResNet-18 from scratch on CPU,
8 epochs. Nothing is edited afterwards: the log is main.py's output, byte for
byte.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.datasets import load_digits

HERE = Path(__file__).resolve().parent
DATA = HERE / "digits"
EPOCHS = sys.argv[1] if len(sys.argv) > 1 else "8"
TRAIN_EACH, VAL_EACH = 100, 30

ARGS = [
    "digits",
    "--arch=resnet18",
    f"--epochs={EPOCHS}",
    "--batch-size=32",
    "--lr=0.01",
    "--workers=0",
    "--print-freq=5",
    "--no-accel",
]


def image_folder() -> None:
    """The digits as `digits/{train,val}/<class>/<n>.png`, written once."""
    if DATA.is_dir():
        return
    images, labels = load_digits(return_X_y=True)
    kept = dict.fromkeys(range(10), 0)
    for pixels, label in zip(images, labels, strict=True):
        n = kept[int(label)]
        if n >= TRAIN_EACH + VAL_EACH:
            continue
        kept[int(label)] = n + 1
        folder = DATA / ("train" if n < TRAIN_EACH else "val") / str(int(label))
        folder.mkdir(parents=True, exist_ok=True)
        grey = (pixels.reshape(8, 8) * (255 / 16)).astype(np.uint8)
        Image.fromarray(grey).convert("RGB").resize((32, 32), Image.NEAREST).save(
            folder / f"{n:03d}.png"
        )


def main() -> None:
    image_folder()
    # main.py writes its checkpoints into the folder it runs in.
    subprocess.run(  # noqa: S603 - the PyTorch example itself, with the arguments above
        [sys.executable, "-u", str(HERE / "examples" / "imagenet" / "main.py"), *ARGS],
        cwd=HERE,
        check=True,
    )


if __name__ == "__main__":
    main()
