"""A run that reports F1 has a task, and a story.

The docs list `f1` as a classification metric and `epochix check` names F1 as
"task-defining". The task classifier did not agree: F1 was no signal, so a log
reporting it fell to the `custom` task, whose story is told on a loss.

* A log with **only** F1 produced no frame at all — no story, no grade.
* A log with F1 and a loss was told on the loss, and F1 was ignored.
* `epochix check`, given a log containing `val_f1`, answered "No task-defining
  metric (accuracy / mAP / F1 / MAE / perplexity ...)".

Each case goes through `parse()` and the CLI, the way a user meets it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from epochix import parse
from epochix.cli import app
from epochix.enums import TaskType
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.grade import compute_grade, has_absolute_scale
from epochix.story_engine.task_classifier import classify_task

if TYPE_CHECKING:
    from pathlib import Path

    from epochix.models import Run, StoryFrame

runner = CliRunner()

F1 = [0.40, 0.55, 0.70, 0.80, 0.84]


def _told(tmp_path: Path, lines: list[str]) -> tuple[Run, list[StoryFrame]]:
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="f1")
    return run, RunStore(db_path=db).get_story_frames(run.id)


def _f1_only() -> list[str]:
    return [f"Epoch {e}/5 val_f1={v}" for e, v in enumerate(F1, start=1)]


def _f1_and_loss() -> list[str]:
    return [
        f"Epoch {e}/5 train_loss={1 / e:.3f} val_loss={1.2 / e:.3f} val_f1={v}"
        for e, v in enumerate(F1, start=1)
    ]


class TestTheClassifier:
    @pytest.mark.parametrize("key", ["f1", "val_f1"])
    def test_f1_says_classification(self, key: str) -> None:
        assert classify_task({key}) is TaskType.CLASSIFICATION
        assert classify_task({key, "train_loss", "val_loss"}) is TaskType.CLASSIFICATION

    @pytest.mark.parametrize(
        ("beside", "task"),
        [
            ("mAP50", TaskType.DETECTION),
            ("mIoU", TaskType.SEGMENTATION),
            ("perplexity", TaskType.NLP),
            ("EER", TaskType.BIOMETRIC),
        ],
    )
    def test_a_more_specific_metric_beside_it_still_decides(
        self, beside: str, task: TaskType
    ) -> None:
        """Detectors and taggers print F1 too; it is the weakest signal."""
        assert classify_task({"f1", beside}) is task


class TestTheStory:
    def test_a_log_with_only_f1_is_told(self, tmp_path: Path) -> None:
        run, frames = _told(tmp_path, _f1_only())
        assert run.task_type is TaskType.CLASSIFICATION
        assert [f.primary_metric for f in frames] == ["val_f1"] * 5
        assert [f.primary_metric_value for f in frames] == F1
        assert [f.epoch for f in frames] == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_f1_beside_a_loss_is_the_story_not_the_loss(self, tmp_path: Path) -> None:
        run, frames = _told(tmp_path, _f1_and_loss())
        assert run.task_type is TaskType.CLASSIFICATION
        assert {f.primary_metric for f in frames} == {"val_f1"}
        assert len(frames) == 5

    def test_accuracy_beside_it_still_tells_the_story(self, tmp_path: Path) -> None:
        lines = [
            f"Epoch {e}/5 val_accuracy={v + 0.05:.3f} val_f1={v}" for e, v in enumerate(F1, start=1)
        ]
        _, frames = _told(tmp_path, lines)
        assert {f.primary_metric for f in frames} == {"val_accuracy"}

    def test_it_is_graded_where_it_stands(self, tmp_path: Path) -> None:
        """F1 shares accuracy's bands (see test_f1_grade_scale.py): every frame
        is graded on its value, the first included."""
        assert has_absolute_scale("val_f1")
        _, frames = _told(tmp_path, _f1_only())
        for frame in frames:
            assert frame.grade is compute_grade(
                TaskType.CLASSIFICATION, frame.primary_metric_value
            ), frame.epoch
            assert frame.grade_basis == "thresholds"


class TestCheck:
    @pytest.mark.parametrize("lines", [_f1_only(), _f1_and_loss()], ids=["f1_only", "f1_and_loss"])
    def test_it_does_not_ask_for_the_metric_the_log_has(
        self, tmp_path: Path, lines: list[str]
    ) -> None:
        log = tmp_path / "run.log"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = runner.invoke(app, ["check", str(log)])
        assert result.exit_code == 0, result.output
        assert "val_f1" in result.output
        assert "classification" in result.output
        assert "No task-defining metric" not in result.output

    def test_a_loss_only_log_is_still_told_what_to_add(self, tmp_path: Path) -> None:
        """Guard: the hint must not have disappeared for the runs it is for."""
        log = tmp_path / "run.log"
        log.write_text(
            "\n".join(f"Epoch {e}/5 train_loss={1 / e:.3f}" for e in range(1, 6)) + "\n",
            encoding="utf-8",
        )
        result = runner.invoke(app, ["check", str(log)])
        assert result.exit_code == 0, result.output
        assert "No task-defining metric" in result.output
