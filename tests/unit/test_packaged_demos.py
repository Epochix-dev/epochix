"""`epochix demo` plays exactly the logs the repository shows.

The package ships its own copies of the demo logs (`src/epochix/_demos/`), and
nothing tied them to `demo/`, where the README, the corpus truth and the tests
read them. Regenerating the Keras demo in `demo/` would have left
`epochix demo keras` playing the old, hand-written log — the one this change
replaced — while every test passed against the new one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PACKAGED = sorted((REPO / "src" / "epochix" / "_demos").glob("*.log"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_the_package_ships_demos() -> None:
    # Guard: an empty glob would pass the parametrised check below vacuously.
    assert {p.name for p in PACKAGED} >= {
        "keras_image_classifier.log",
        "seq2seq_attention.log",
        "yolov8_detection.log",
    }


@pytest.mark.parametrize("packaged", PACKAGED, ids=[p.name for p in PACKAGED])
def test_each_packaged_demo_is_the_repository_demo(packaged: Path) -> None:
    source = REPO / "demo" / packaged.name
    assert source.is_file(), f"{packaged.name} ships without a demo/ original"
    assert _text(packaged).strip(), f"{packaged.name} is empty"
    assert _text(packaged) == _text(source), f"src/epochix/_demos/{packaged.name} drifted"


def test_the_keras_demo_is_a_complete_real_run() -> None:
    """Every epoch present, and the model summary Keras could actually print."""
    text = _text(REPO / "demo" / "keras_image_classifier.log")
    epochs = [
        int(ln.split()[1].split("/")[0]) for ln in text.splitlines() if ln.startswith("Epoch ")
    ]
    assert epochs == list(range(1, 21))
    assert "flatten (Flatten)" in text
    assert (REPO / "demo" / "keras_image_classifier_source.py").is_file()
