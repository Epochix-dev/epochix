"""A metric that cannot change the grade is not supported, only parsed.

0.5.46 added twenty canonical metric keys and wired exactly one of them
(segmentation) into task detection and primary-metric selection. The rest
parsed correctly, were charted, and then had no effect: a run whose MAPE
improved from 0.31 to 0.08 and one whose MAPE *worsened* from 0.08 to 0.31
both came back ``task=custom, primary=val_loss, grade=D``. Indistinguishable.

The check that exposed it is the one worth keeping: feed the same metric
improving and worsening, and require the grades to differ in the right
direction. It also caught two deeper faults:

* **R² was graded backwards.** Direction was decided per *task*, and R² lives
  in ``regression`` alongside error metrics, so improving scored worse than
  worsening.
* **PSNR and WER were graded against the wrong scale** — the ``generative``
  bands are built for FID and the ``nlp`` bands for perplexity, so both graded
  A+ whichever way they moved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from epochix import parse

if TYPE_CHECKING:
    from pathlib import Path

# Best grade first — a lower index is a better grade.
_GRADE_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F", "I"]

# (metric key as logged, values that improve over six epochs)
_METRICS: list[tuple[str, list[float]]] = [
    ("val_acc", [0.30, 0.55, 0.70, 0.80, 0.88, 0.94]),
    ("val_auc", [0.55, 0.66, 0.74, 0.81, 0.87, 0.93]),
    ("val_iou", [0.31, 0.45, 0.56, 0.63, 0.68, 0.74]),
    ("val_dice", [0.35, 0.50, 0.61, 0.69, 0.75, 0.80]),
    ("val_r2", [0.20, 0.38, 0.55, 0.68, 0.79, 0.88]),
    ("val_mape", [0.31, 0.24, 0.19, 0.15, 0.11, 0.08]),
    ("val_psnr", [18.2, 21.4, 24.1, 26.5, 28.3, 30.1]),
    ("val_ssim", [0.61, 0.70, 0.77, 0.83, 0.88, 0.92]),
    ("val_wer", [0.62, 0.48, 0.37, 0.28, 0.21, 0.15]),
    ("val_cer", [0.40, 0.31, 0.24, 0.18, 0.13, 0.09]),
]


def _grade(tmp_path: Path, name: str, key: str, values: list[float]) -> tuple[str, str]:
    log = tmp_path / f"{name}.log"
    log.write_text(
        "".join(
            f"Epoch {i}/{len(values)} train_loss=0.5 {key}={v}\n" for i, v in enumerate(values, 1)
        ),
        encoding="utf-8",
    )
    run = parse(log, db=str(tmp_path / "runs.db"), run_name=name)
    return (
        run.final_grade.value if run.final_grade else "I",
        run.primary_metric or "",
    )


@pytest.mark.parametrize(("key", "improving"), _METRICS, ids=[m[0] for m in _METRICS])
def test_improving_beats_worsening(key: str, improving: list[float], tmp_path: Path) -> None:
    """The whole point of recognising a metric: it has to move the grade."""
    up_grade, up_primary = _grade(tmp_path, f"{key}_up", key, improving)
    down_grade, down_primary = _grade(tmp_path, f"{key}_dn", key, list(reversed(improving)))

    assert up_grade != down_grade, (
        f"{key}: improving and worsening both graded {up_grade} — "
        "the metric is parsed but does not reach the grade"
    )
    assert _GRADE_ORDER.index(up_grade) < _GRADE_ORDER.index(down_grade), (
        f"{key}: graded BACKWARDS — improving={up_grade}, worsening={down_grade}"
    )
    assert up_primary == down_primary, (
        f"{key}: primary metric differs between the two runs ({up_primary} vs {down_primary})"
    )


@pytest.mark.parametrize(("key", "improving"), _METRICS, ids=[m[0] for m in _METRICS])
def test_the_metric_becomes_the_primary(key: str, improving: list[float], tmp_path: Path) -> None:
    """It must not silently fall back to train_loss, which is what happened."""
    _, primary = _grade(tmp_path, f"{key}_primary", key, improving)
    assert primary and primary != "train_loss", (
        f"{key}: the run graded on {primary!r} instead of the metric it logged"
    )
