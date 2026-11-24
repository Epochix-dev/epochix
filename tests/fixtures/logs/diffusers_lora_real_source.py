"""Train an SDXL LoRA with the diffusers DreamBooth script, console output kept.

`examples/dreambooth/train_dreambooth_lora_sdxl.py` (github.com/huggingface/
diffusers) counts optimisation steps, not epochs, and draws ONE tqdm bar for
the whole run. The loss of the last batch and the learning rate ride on the
bar; nothing else is ever printed about how the training is going:

    Steps:  32%|###2      | 39/120 [00:26<00:43,  1.85it/s, loss=0.0129, lr=0.0001]

    Needs:  pip install torch torchvision diffusers transformers accelerate peft
                        sentencepiece ftfy tensorboard pillow
            diffusers/   git clone --branch v0.42.1 https://github.com/huggingface/diffusers
            sdxl-base/   stabilityai/stable-diffusion-xl-base-1.0 as a folder in
                         the diffusers layout (model_index.json, unet/, vae/,
                         text_encoder/, text_encoder_2/, tokenizer/,
                         tokenizer_2/, scheduler/; about 14 GB). A folder
                         beside this file, not the Hugging Face cache: the
                         libraries print the path they load from, and the
                         cache is in the user's profile.
            a GPU
    Run:    python diffusers_lora_real_source.py > diffusers_lora_real.log 2>&1

Run from a neutral folder. The pictures it trains on are drawn here: twelve
512-pixel images of a few coloured shapes each. A rank-4 LoRA, 120 steps, a
constant learning rate, a checkpoint every 40 steps. The run shows the
trainer's output; twelve drawings and 120 steps teach a diffusion model
nothing worth keeping. Nothing is edited afterwards: the log is the script's
output, byte for byte, the bar's redraws included.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
DATA = HERE / "shapes"
STEPS = sys.argv[1] if len(sys.argv) > 1 else "120"

ARGS = [
    "--pretrained_model_name_or_path=sdxl-base",
    "--instance_data_dir=shapes",
    "--output_dir=lora_out",
    "--instance_prompt=a flat drawing of coloured shapes",
    "--resolution=512",
    "--train_batch_size=1",
    "--learning_rate=1e-4",
    "--lr_scheduler=constant",
    "--lr_warmup_steps=0",
    f"--max_train_steps={STEPS}",
    "--checkpointing_steps=40",
    "--mixed_precision=fp16",
    "--rank=4",
    "--seed=0",
]


def pictures() -> None:
    """Twelve drawings of circles and rectangles, written once."""
    if DATA.is_dir():
        return
    DATA.mkdir()
    rng = random.Random(0)  # noqa: S311 - drawing, not cryptography
    for n in range(12):
        image = Image.new("RGB", (512, 512), (245, 240, 230))
        draw = ImageDraw.Draw(image)
        for _ in range(5):
            x, y = rng.randrange(40, 380), rng.randrange(40, 380)
            size = rng.randrange(60, 130)
            colour = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            shape = draw.ellipse if rng.random() < 0.5 else draw.rectangle
            shape((x, y, x + size, y + size), fill=colour)
        image.save(DATA / f"{n:02d}.png")


def main() -> None:
    pictures()
    script = HERE / "diffusers" / "examples" / "dreambooth" / "train_dreambooth_lora_sdxl.py"
    subprocess.run(  # noqa: S603 - the diffusers example itself, with the arguments above
        [sys.executable, "-u", str(script), *ARGS],
        cwd=HERE,
        check=True,
        # The base model comes from the folder beside this file or not at all.
        env={**os.environ, "HF_HUB_OFFLINE": "1"},
    )


if __name__ == "__main__":
    main()
