"""Fine-tune YOLOv8n on COCO128 for real and keep Ultralytics' own console output.

COCO128 is Ultralytics' tutorial dataset: the first 128 images of COCO
train2017, used for both training and validation. The mAP it reports is
therefore measured on images the model trains on — it shows the detector
fitting those images, not how it generalises.

    Needs:  pip install ultralytics
            coco128/      from github.com/ultralytics/assets (coco128.zip, 7 MB)
            yolov8n.pt    the pretrained COCO checkpoint
    Run:    python yolov8_detection_source.py > yolov8_detection.log 2>&1

Nothing is edited afterwards: the log is the console output, byte for byte,
progress-bar redraws included.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from ultralytics import YOLO
from ultralytics.utils import ROOT

HERE = Path(__file__).resolve().parent
EPOCHS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
DATASET = sys.argv[2] if len(sys.argv) > 2 else "coco128"
IMGSZ = int(sys.argv[3]) if len(sys.argv) > 3 else 640
DEVICE = sys.argv[4] if len(sys.argv) > 4 else "0"


def dataset_yaml() -> Path:
    """Ultralytics' own dataset definition, pointed at the copy beside this file."""
    spec = yaml.safe_load(
        (ROOT / "cfg" / "datasets" / f"{DATASET}.yaml").read_text(encoding="utf-8")
    )
    spec["path"] = str(HERE / DATASET)
    spec.pop("download", None)
    out = HERE / f"{DATASET}.local.yaml"
    out.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return out


def main() -> None:
    model = YOLO(str(HERE / "yolov8n.pt"))
    model.train(
        data=str(dataset_yaml()),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=16,
        device=DEVICE,
        workers=0,
        seed=0,
        amp=False,
        plots=False,
        project=str(HERE / "runs"),
        name=f"{DATASET}_{EPOCHS}ep",
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
