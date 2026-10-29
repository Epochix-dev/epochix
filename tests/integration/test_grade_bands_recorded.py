"""A run records the grade bands its letter was measured against.

The learning curve drew dashed grade lines from a typed copy of
classification's bands (A+ 0.97, A 0.93, … C 0.55), for every percentage
metric. The engine's own classification bands are A+ 0.95, A 0.90, … C 0.60,
detection's run from 0.75 down, and AUC has bands of its own: a run graded
A+ at 0.95 sat below the chart's A+ line. The run now carries the bands the
grader used (`config.grade_bands`), and the chart draws those.
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any

import pytest

from epochix import parse
from epochix.enums import Grade, TaskType
from epochix.ingester.file_batch import FileBatchIngester
from epochix.pipeline import run_pipeline
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.grade import grade_bands

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "tests" / "fixtures" / "logs"


def _recorded(log: Path) -> tuple[Any, Any]:
    store = RunStore(":memory:")
    asyncio.run(
        run_pipeline(ingester=FileBatchIngester("r", str(log)), run_id="r", store=store, hub=Hub())
    )
    run = store.get_run("r")
    assert run is not None
    return run, (run.config or {}).get("grade_bands")


def _finite(task: TaskType, metric: str) -> list[dict[str, Any]]:
    rows, _ = grade_bands(task, metric=metric)
    return [
        {"grade": g.value, "value": v} for g, v in rows if v not in (float("inf"), float("-inf"))
    ]


@pytest.mark.parametrize(
    ("log", "task", "metric"),
    [
        (ROOT / "demo" / "keras_image_classifier.log", TaskType.CLASSIFICATION, "val_accuracy"),
        (ROOT / "demo" / "yolov8_detection.log", TaskType.DETECTION, "mAP50"),
        (LOGS / "lightgbm_real_classifier.log", TaskType.CLASSIFICATION, "val_AUC"),
    ],
    ids=lambda v: getattr(v, "name", str(v)),
)
def test_a_run_graded_on_bands_records_the_engine_s_bands(
    log: Path, task: TaskType, metric: str
) -> None:
    run, bands = _recorded(log)
    assert run.primary_metric == metric
    assert bands is not None, "the run graded on bands recorded none"
    assert bands["lower_better"] is False
    assert bands["bands"] == _finite(task, metric)


def test_the_bands_are_not_the_dashboard_s_old_copy() -> None:
    """The copy the chart drew: A+ 0.97, A 0.93. The grader's: A+ 0.95, A 0.90."""
    _, bands = _recorded(ROOT / "demo" / "keras_image_classifier.log")
    assert bands["bands"][:2] == [{"grade": "A+", "value": 0.95}, {"grade": "A", "value": 0.9}]


def test_a_run_graded_on_improvement_records_none() -> None:
    _, bands = _recorded(LOGS / "catboost_real_classifier.log")
    assert bands is None


def test_a_project_s_own_bands_are_the_ones_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EPOCHIX_GRADE_CONFIG", "")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")
    (tmp_path / ".epochix.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            grade_thresholds:
              classification:
                "A+": 0.999
                A: 0.998
                B: 0.997
            """
        ),
        encoding="utf-8",
    )
    log = tmp_path / "run.log"
    rows = [
        f"Epoch {e}/3 train_loss={1 / e:.3f} val_accuracy={v}"
        for e, v in [(1, 0.8), (2, 0.85), (3, 0.9)]
    ]
    log.write_text("\n".join(rows) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="t")
    store = RunStore(db_path=db)
    assert store.get_story_frames(run.id)[-1].grade is Grade.F
    bands = (store.get_run(run.id).config or {})["grade_bands"]
    assert [b["value"] for b in bands["bands"]] == [0.999, 0.998, 0.997]
