"""Train an SDXL LoRA with kohya-ss sd-scripts, console output kept.

`sdxl_train_network.py` (github.com/kohya-ss/sd-scripts) counts optimisation
steps and draws ONE tqdm bar for the whole run, described "steps". The moving
average of the loss rides on it as `avr_loss`; between epochs the script
prints `epoch N/M` on a line of its own.

    Needs:  pip install torch torchvision   (a CUDA build)
            sd-scripts/  git clone --branch v0.9.1 https://github.com/kohya-ss/sd-scripts
                         then pip install -r sd-scripts/requirements.txt
                         from inside it, and pip install "numpy<2": its
                         opencv-python 4.8 does not import under numpy 2
            sdxl-base/   stabilityai/stable-diffusion-xl-base-1.0 as a folder in
                         the diffusers layout (model_index.json, unet/, vae/,
                         text_encoder/, text_encoder_2/, tokenizer/,
                         tokenizer_2/, scheduler/; about 14 GB). A folder
                         beside this file, not the Hugging Face cache: the
                         libraries print the path they load from, and the
                         cache is in the user's profile.
            a GPU
    Run:    python kohya_lora_real_source.py > kohya_lora_real.log 2>&1

Run from a neutral folder. sd-scripts asks the Hugging Face Hub for the two
CLIP tokenizers by name (openai/clip-vit-large-patch14 and
laion/CLIP-ViT-bigG-14-laion2B-39B-b160k) unless they are in its
`--tokenizer_cache_dir`; they are put there from sdxl-base/tokenizer and
sdxl-base/tokenizer_2, which are those two tokenizers, so nothing is fetched.

The pictures it trains on are drawn here: twelve 512-pixel images of a few
coloured shapes each, one caption each. A rank-4 LoRA on the U-Net only, 120
steps (ten epochs of twelve), a constant learning rate, a checkpoint every 40
steps. The run shows the trainer's output; twelve drawings and 120 steps teach
a diffusion model nothing worth keeping. Nothing is edited afterwards: the log
is the script's output, byte for byte, the bar's redraws included.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
DATA = HERE / "shapes" / "1_shapes"  # sd-scripts' layout: <repeats>_<name>
TOKENIZERS = HERE / "tokenizers"
CAPTION = "a flat drawing of coloured shapes"
STEPS = sys.argv[1] if len(sys.argv) > 1 else "120"

ARGS = [
    "--pretrained_model_name_or_path=sdxl-base",
    "--train_data_dir=shapes",
    "--caption_extension=.txt",
    "--output_dir=lora_out",
    "--output_name=shapes",
    "--save_model_as=safetensors",
    "--tokenizer_cache_dir=tokenizers",
    "--resolution=512",
    "--train_batch_size=1",
    "--network_module=networks.lora",
    "--network_dim=4",
    "--network_alpha=1",
    "--network_train_unet_only",
    "--cache_text_encoder_outputs",
    "--cache_latents",
    "--no_half_vae",
    "--gradient_checkpointing",
    "--sdpa",
    "--optimizer_type=AdamW",
    "--learning_rate=1e-4",
    "--lr_scheduler=constant",
    f"--max_train_steps={STEPS}",
    "--save_every_n_steps=40",
    "--mixed_precision=fp16",
    "--save_precision=fp16",
    "--max_data_loader_n_workers=0",
    "--seed=0",
]


def pictures() -> None:
    """Twelve drawings of circles and rectangles, written once."""
    if DATA.is_dir():
        return
    DATA.mkdir(parents=True)
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
        (DATA / f"{n:02d}.txt").write_text(CAPTION, encoding="utf-8")


def tokenizers() -> None:
    """The two tokenizers, where sd-scripts looks before asking the Hub."""
    for name, folder in (
        ("openai_clip-vit-large-patch14", "tokenizer"),
        ("laion_CLIP-ViT-bigG-14-laion2B-39B-b160k", "tokenizer_2"),
    ):
        if not (TOKENIZERS / name).is_dir():
            shutil.copytree(HERE / "sdxl-base" / folder, TOKENIZERS / name)


def main() -> None:
    pictures()
    tokenizers()
    script = HERE / "sd-scripts" / "sdxl_train_network.py"
    subprocess.run(  # noqa: S603 - sd-scripts itself, with the arguments above
        [sys.executable, "-u", str(script), *ARGS],
        cwd=HERE,
        check=True,
        env={
            **os.environ,
            # The base model and tokenizers come from the folders beside this
            # file or not at all.
            "HF_HUB_OFFLINE": "1",
            # sd-scripts prints Japanese beside its English; a redirected
            # stdout on Windows is not UTF-8 otherwise, and the print fails.
            "PYTHONIOENCODING": "utf-8",
        },
    )


if __name__ == "__main__":
    main()
