"""Convert Apple GazeCapture into a YOLO eye-detection dataset.

GazeCapture ships per-subject folders (00002/, 00003/, …) each containing
``frames/*.jpg`` plus ``appleLeftEye.json`` and ``appleRightEye.json`` — these
JSON files list ``{X, Y, W, H, IsValid}`` arrays in pixel coordinates indexed
by frame number. We:

1. Walk the subject folders under <source>/00*.tar/<subject>/
2. For every frame where both eyes are valid, read the image to learn its
   dimensions and write a YOLO label file with two boxes (class 0 = eye)
   normalised to [0,1].
3. Split frames 80 / 20 train / val.
4. Emit a YOLO ``data.yaml`` pointing at the produced directory.

Usage:
    python scripts/gazecapture_to_yolo.py \\
        --src "C:/Work/Universitry/Deep Learning models/Dataset" \\
        --dst eye_yolo \\
        --max-subjects 3 \\
        --max-per-subject 200

After running, train with (once your torch DLL is unblocked):

    yolo train data=eye_yolo/data.yaml model=yolov8n.pt epochs=30 imgsz=320 \\
        batch=16 device=0 2>&1 | epochix --live
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

try:
    from PIL import Image
except Exception as exc:  # noqa: BLE001
    sys.exit(
        "Pillow is required to read frame dimensions. "
        f"`pip install pillow` first ({exc})."
    )


def _iter_subjects(src: Path):
    """Yield (subject_id, subject_dir) for each subject in the dataset."""
    for tarred in sorted(src.glob("*.tar")):
        if not tarred.is_dir():
            continue
        # Each "*.tar" entry is actually a directory containing one folder
        # named after the subject id.
        for sub in tarred.iterdir():
            if sub.is_dir() and (sub / "appleLeftEye.json").is_file():
                yield sub.name, sub


def _load_eye_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _yolo_box(x: float, y: float, w: float, h: float, im_w: int, im_h: int) -> str:
    """One YOLO box line: 'cls cx cy w h' normalised to [0,1]."""
    cx = (x + w / 2.0) / im_w
    cy = (y + h / 2.0) / im_h
    nw = w / im_w
    nh = h / im_h
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    nw = max(0.0, min(1.0, nw))
    nh = max(0.0, min(1.0, nh))
    return f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def convert(
    src: Path,
    dst: Path,
    *,
    max_subjects: int | None,
    max_per_subject: int | None,
    val_ratio: float = 0.2,
    seed: int = 0,
) -> tuple[int, int]:
    """Convert subjects under *src* into a YOLO dataset rooted at *dst*.

    Returns (train_count, val_count).
    """
    rng = random.Random(seed)
    train_img = dst / "images" / "train"
    val_img = dst / "images" / "val"
    train_lbl = dst / "labels" / "train"
    val_lbl = dst / "labels" / "val"
    for d in (train_img, val_img, train_lbl, val_lbl):
        d.mkdir(parents=True, exist_ok=True)

    train_n = val_n = 0
    seen_subjects = 0
    for sid, sub in _iter_subjects(src):
        if max_subjects is not None and seen_subjects >= max_subjects:
            break
        seen_subjects += 1
        left = _load_eye_json(sub / "appleLeftEye.json")
        right = _load_eye_json(sub / "appleRightEye.json")
        frames_dir = sub / "frames"
        # GazeCapture JSON arrays are aligned by frame index. We accept a
        # frame only when both eyes are marked valid.
        n = min(len(left.get("X", [])), len(right.get("X", [])))
        kept = 0
        for i in range(n):
            if not (left["IsValid"][i] and right["IsValid"][i]):
                continue
            frame_path = frames_dir / f"{i:05d}.jpg"
            if not frame_path.is_file():
                continue
            try:
                with Image.open(frame_path) as im:
                    im_w, im_h = im.size
            except Exception:  # noqa: BLE001
                continue
            lines = [
                _yolo_box(left["X"][i], left["Y"][i],
                         left["W"][i], left["H"][i], im_w, im_h),
                _yolo_box(right["X"][i], right["Y"][i],
                         right["W"][i], right["H"][i], im_w, im_h),
            ]
            is_val = rng.random() < val_ratio
            tgt_img = (val_img if is_val else train_img) / f"{sid}_{i:05d}.jpg"
            tgt_lbl = (val_lbl if is_val else train_lbl) / f"{sid}_{i:05d}.txt"
            # Hard-link instead of copying — instant + saves disk space.
            try:
                tgt_img.hardlink_to(frame_path)
            except (OSError, FileExistsError):
                # Fall back to a regular copy if hardlink is not supported
                # (e.g. across volumes) or already exists.
                import shutil
                if not tgt_img.exists():
                    shutil.copy2(frame_path, tgt_img)
            tgt_lbl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            if is_val:
                val_n += 1
            else:
                train_n += 1
            kept += 1
            if max_per_subject is not None and kept >= max_per_subject:
                break
        print(f"  subject {sid}: kept {kept} frames")

    # Emit data.yaml — ultralytics consumes this directly.
    data_yaml = dst / "data.yaml"
    data_yaml.write_text(
        f"path: {dst.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: eye\n",
        encoding="utf-8",
    )
    return train_n, val_n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, type=Path,
                    help="GazeCapture root (contains 00*.tar/ directories)")
    ap.add_argument("--dst", required=True, type=Path,
                    help="Output directory for the YOLO dataset")
    ap.add_argument("--max-subjects", type=int, default=None,
                    help="Stop after this many subjects (good for a quick demo)")
    ap.add_argument("--max-per-subject", type=int, default=None,
                    help="Stop after this many valid frames per subject")
    args = ap.parse_args()

    if not args.src.is_dir():
        sys.exit(f"--src not found: {args.src}")

    train_n, val_n = convert(
        args.src, args.dst,
        max_subjects=args.max_subjects,
        max_per_subject=args.max_per_subject,
    )
    print()
    print(f"✅ Wrote {train_n} train + {val_n} val frames → {args.dst}")
    print(f"   data.yaml: {args.dst / 'data.yaml'}")
    print()
    print("Train (after unblocking torch DLL):")
    print(f"   yolo train data={args.dst}/data.yaml model=yolov8n.pt "
          f"epochs=30 imgsz=320 batch=16 device=0 2>&1 | epochix --live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
