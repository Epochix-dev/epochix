"""A run is compared, tabulated and animated on the metric it is graded on.

A story can start on one metric and move to another: `demo/pytorch_lightning.log`
prints training accuracy for nine epochs and first validates at epoch 10. Its
story, its grade (A-) and its last value (0.876) are on `val_accuracy`. The
comparison took each run on the metric *most of its frames* carried, so:

* compared with a run on `val_accuracy` it was called "not comparable
  (accuracy, val_accuracy)", and its row read `accuracy`, 0.719, best at
  epoch 9, beside the A- and "against fixed thresholds for this metric";
* two detection runs graded on mAP50 were ranked on their box loss;
* its default GIF was nine epochs of training accuracy over "final grade A-".

Measured over the corpus on 2026-11-10: of the 55 logs that tell a story, 12
change metric once. The majority metric was not the graded one in 3 of them;
the latest frame's metric was in none. So the rule is the latest frame's, which
is also how the dashboard names the story's metric (`latestPrimaryKey`).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import epochix.cli as cli
from epochix import parse
from epochix.config import Settings
from epochix.exporters.compare_export import build_comparison
from epochix.exporters.gif_export import _series_for, build_gif
from epochix.ingester.file_batch import FileBatchIngester
from epochix.models import StoryFrame
from epochix.pipeline import run_pipeline
from epochix.server.app import create_app
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.comparison import told_on, trajectory_from_frames

ROOT = Path(__file__).resolve().parents[2]
TRUTH: dict[str, dict[str, Any]] = json.loads(
    (ROOT / "tests" / "fixtures" / "corpus_truth.json").read_text(encoding="utf-8")
)

# Validates late: 9 frames of `accuracy`, then 5 of `val_accuracy`.
LATE = "pytorch_lightning.log"
STEADY = "keras_image_classifier.log"
# Graded on mAP50; `box_loss` has as many frames, or more.
DETECTION = ("yolo_short.log", "detection_coco.log")
# The logs where the majority metric is not the graded one.
MAJORITY_WAS_WRONG = {LATE, *DETECTION}


def _path(name: str) -> Path:
    return ROOT / TRUTH[name]["path"]


# ── the rule, over every log ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def corpus_frames() -> dict[str, list[StoryFrame]]:
    """Every corpus log through the real pipeline, once."""
    out: dict[str, list[StoryFrame]] = {}
    for name in sorted(TRUTH):
        store = RunStore(":memory:")
        asyncio.run(
            run_pipeline(
                ingester=FileBatchIngester("c", str(_path(name))),
                run_id="c",
                store=store,
                hub=Hub(),
            )
        )
        out[name] = store.get_story_frames("c")
    return out


def test_the_corpus_still_has_runs_that_change_metric(
    corpus_frames: dict[str, list[StoryFrame]],
) -> None:
    """Or the test below compares one rule with itself and proves nothing."""
    majority_differs = set()
    for name, frames in corpus_frames.items():
        counts: dict[str, int] = {}
        for frame in frames:
            if frame.primary_metric:
                counts[frame.primary_metric] = counts.get(frame.primary_metric, 0) + 1
        if counts and max(counts, key=lambda k: counts[k]) != TRUTH[name]["metric"]:
            majority_differs.add(name)
    assert majority_differs == MAJORITY_WAS_WRONG


@pytest.mark.parametrize("name", sorted(TRUTH))
def test_a_run_is_compared_on_the_metric_its_story_is_told_on(
    name: str, corpus_frames: dict[str, list[StoryFrame]]
) -> None:
    frames = corpus_frames[name]
    want = TRUTH[name]
    assert told_on(frames) == want["metric"]

    trajectory = trajectory_from_frames(name, list(frames))
    on_metric = [f for f in frames if f.primary_metric == want["metric"] and f.epoch is not None]
    if len(on_metric) < 2:
        # One reading of the story's metric is not a trajectory, however many
        # readings of another metric came before it.
        assert trajectory is None
        return
    assert trajectory is not None
    assert trajectory.primary_metric == want["metric"]
    assert len(trajectory.values) == len(on_metric)
    assert round(trajectory.final_value, 4) == want["last_value"]


# ── the surfaces: export, CLI, API, GIF ───────────────────────────────────────


def _stored(tmp_path: Path, *names: str) -> tuple[Path, list[str]]:
    db = tmp_path / "runs.db"
    ids = [parse(_path(name), db=str(db), run_name=Path(name).stem).id for name in names]
    return db, ids


def test_a_run_that_validates_late_is_compared_on_its_validation_metric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    late, steady = TRUTH[LATE], TRUTH[STEADY]
    assert late["metric"] == steady["metric"] == "val_accuracy"
    assert late["metric_from_epoch"] == 10.0
    db, (a, b) = _stored(tmp_path, LATE, STEADY)

    comparison = build_comparison([a, b], RunStore(db_path=str(db)))

    assert "not comparable" not in comparison.narrative
    assert comparison.narrative.startswith(
        "keras_image_classifier finished ahead of pytorch_lightning: "
        f"{steady['last_value']:.4f} against {late['last_value']:.4f} (val_accuracy)."
    )
    row = comparison.rows[0]
    assert row.grade == late["final_grade"] == "A-"
    assert row.metric == "val_accuracy"
    assert row.final == f"{late['last_value']:.4g}"
    assert row.best == f"{late['last_value']:.4g} (epoch 30)"
    # Five readings of it (epochs 10 to 30), not the fourteen frames.
    assert row.epochs == "5"

    # The same paragraph from the API the comparison view reads, and the CLI.
    with TestClient(create_app(Settings(db=str(db)))) as client:
        served = client.get(f"/api/compare?run_ids={a},{b}").json()["narrative"]
    assert served == comparison.narrative
    monkeypatch.setenv("EPOCHIX_DB", str(db))
    printed = CliRunner().invoke(cli.app, ["compare", a, b])
    assert printed.exit_code == 0, printed.output
    assert "(val_accuracy)" in printed.output
    assert "| `val_accuracy` | 0.876 |" in printed.output
    assert "`accuracy`" not in printed.output


def test_detection_runs_are_ranked_on_map_not_on_box_loss(tmp_path: Path) -> None:
    for name in DETECTION:
        assert TRUTH[name]["metric"] == "mAP50"
    db, ids = _stored(tmp_path, *DETECTION)

    comparison = build_comparison(ids, RunStore(db_path=str(db)))

    assert "(mAP50)" in comparison.narrative
    assert "box_loss" not in comparison.narrative
    for row, name in zip(comparison.rows, DETECTION, strict=True):
        assert row.metric == "mAP50"
        assert row.final == f"{TRUTH[name]['last_value']:.4g}"
        assert row.grade == TRUTH[name]["final_grade"]


def test_the_default_gif_animates_the_graded_metric(tmp_path: Path) -> None:
    db, (run_id,) = _stored(tmp_path, LATE)
    store = RunStore(db_path=str(db))

    metric, points = _series_for(run_id, store, None)

    assert metric == TRUTH[LATE]["metric"]
    assert points[0][0] == TRUTH[LATE]["metric_from_epoch"]
    assert points[-1] == (30.0, TRUTH[LATE]["last_value"])
    assert build_gif(run_id, store).startswith(b"GIF8")


def test_one_validation_reading_is_not_compared_as_training_accuracy(tmp_path: Path) -> None:
    """The same run, stopped just after its first validation pass.

    Nine readings of training accuracy and one of validation accuracy, graded
    on the one. There is no trajectory of the graded metric to compare or to
    animate, and the nine must not stand in for it.
    """
    cut = tmp_path / "stopped_at_epoch_10.log"
    lines = _path(LATE).read_text(encoding="utf-8").splitlines()
    cut.write_text("\n".join(lines[:25]) + "\n", encoding="utf-8")
    db = tmp_path / "runs.db"
    stopped = parse(cut, db=str(db), run_name="stopped")
    steady = parse(_path(STEADY), db=str(db), run_name="steady")
    store = RunStore(db_path=str(db))
    frames = store.get_story_frames(stopped.id)
    assert [f.primary_metric for f in frames] == ["accuracy"] * 9 + ["val_accuracy"]

    comparison = build_comparison([stopped.id, steady.id], store)

    assert comparison.narrative == "Not enough of the runs have data to compare."
    row = comparison.rows[0]
    assert (row.metric, row.final, row.best, row.epochs) == ("val_accuracy", "0.731", "—", "1")

    with pytest.raises(ValueError, match="too few readings of val_accuracy"):
        build_gif(stopped.id, store)
    # The training curve is still there for whoever asks for it by name.
    assert build_gif(stopped.id, store, metric="accuracy").startswith(b"GIF8")
