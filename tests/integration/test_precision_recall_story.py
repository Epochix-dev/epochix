"""`precision` and `recall` printed by a training loop are read, and tell a story.

docs/training-loop.md listed them as metrics to print. Neither worked:

* `precision` was in the run-configuration skip list, because Lightning and
  AMP print the numeric precision under that name (`precision=16`). Every
  parser dropped the metric: a loop printing `precision=0.55 recall=0.45`
  charted its recall alone, and a Keras bar's `precision: 0.87` vanished.
* `recall` was read, but it is neither a task signal nor on any task's list of
  story metrics, so a log with only these two had task `custom` and no frame.
* `epochix check` then said the run "is graded on how much its loss improved"
  — of a log with no loss in it.

Each case goes through the parsers, `parse()` and the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from epochix import parse
from epochix.cli import app
from epochix.enums import TaskType
from epochix.parsers._never_metrics import NEVER_METRICS, VALUE_DECIDES, is_setting
from epochix.parsers.base import ParserContext
from epochix.parsers.huggingface import HFParser
from epochix.parsers.keras_tensorflow import KerasParser
from epochix.parsers.universal import UniversalParser
from epochix.store.sqlite_store import RunStore
from epochix.story_engine import story_metric
from epochix.story_engine.grade import grade_by_trajectory

if TYPE_CHECKING:
    from pathlib import Path

    from epochix.models import Run, StoryFrame

runner = CliRunner()

PRECISION = [0.55, 0.60, 0.65, 0.70, 0.75]
RECALL = [0.45, 0.50, 0.55, 0.60, 0.65]


def _lines(template: str) -> list[str]:
    return [
        template.format(e=e, p=p, r=r)
        for e, (p, r) in enumerate(zip(PRECISION, RECALL, strict=True), start=1)
    ]


def _told(tmp_path: Path, lines: list[str]) -> tuple[Run, list[StoryFrame]]:
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "runs.db")
    run = parse(log, db=db, run_name="pr")
    return run, RunStore(db_path=db).get_story_frames(run.id)


def _check(tmp_path: Path, lines: list[str]) -> str:
    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(log)])
    assert result.exit_code == 0, result.output
    return result.output


class TestASettingOrAMetric:
    @pytest.mark.parametrize("value", [0.0, 0.55, 0.8700, 1.0])
    def test_a_fraction_is_the_metric(self, value: float) -> None:
        assert not is_setting("precision", value)

    @pytest.mark.parametrize("value", [16.0, 32.0, 64.0, 1.5, -1.0])
    def test_anything_else_is_the_numeric_precision(self, value: float) -> None:
        assert is_setting("precision", value)

    def test_only_the_names_listed_are_decided_by_value(self) -> None:
        assert frozenset({"precision"}) == VALUE_DECIDES
        assert "precision" not in NEVER_METRICS, "the key list would drop it before its value"
        assert not is_setting("recall", 16.0)
        assert not is_setting("accuracy", 99.0)


class TestTheParsers:
    def _universal(self, line: str) -> list[tuple[str, float]]:
        ctx = ParserContext(run_id="t", seq=1)
        return [(m.key, m.value) for m in UniversalParser().parse_line(line, ctx)]

    def test_a_loop_s_precision_is_read(self) -> None:
        assert self._universal("precision=0.55 recall=0.45") == [
            ("precision", 0.55),
            ("recall", 0.45),
        ]
        assert self._universal("precision: 0.55  recall: 0.45") == [
            ("precision", 0.55),
            ("recall", 0.45),
        ]

    @pytest.mark.parametrize("setting", ["precision=16", "precision=32", "precision: 64"])
    def test_the_numeric_precision_is_still_not_a_metric(self, setting: str) -> None:
        assert self._universal(f"{setting} recall=0.45") == [("recall", 0.45)]

    def test_a_keras_bar_keeps_its_precision(self) -> None:
        parser, ctx = KerasParser(), ParserContext(run_id="t")
        parser.parse_line("Epoch 1/5", ctx)
        line = "43/43 - 0s - 5ms/step - loss: 0.42 - precision: 0.8700 - recall: 0.6500"
        assert [(m.key, m.value) for m in parser.parse_line(line, ctx)] == [
            ("loss", 0.42),
            ("precision", 0.87),
            ("recall", 0.65),
        ]

    def test_a_trainer_dict_keeps_its_precision(self) -> None:
        ctx = ParserContext(run_id="t")
        got = HFParser().parse_line("{'precision': 0.81, 'recall': '0.77', 'epoch': 1.0}", ctx)
        assert [(m.key, m.value) for m in got] == [("precision", 0.81), ("recall", 0.77)]


class TestWhichMetricTellsTheStory:
    def test_a_score_no_task_lists_can_carry_a_custom_run(self) -> None:
        assert story_metric(TaskType.CUSTOM, ["precision", "recall"]) == "precision"
        assert story_metric(TaskType.CUSTOM, ["recall"]) == "recall"
        assert story_metric(TaskType.CUSTOM, ["lr", "specificity"]) == "specificity"

    def test_a_loss_still_comes_first(self) -> None:
        assert story_metric(TaskType.CUSTOM, ["recall", "train_loss"]) == "train_loss"

    def test_a_name_we_do_not_recognise_still_comes_before_a_known_score(self) -> None:
        """Unchanged precedence: the run's own metric is told under its name."""
        assert story_metric(TaskType.CUSTOM, ["recall", "my_score"]) == "my_score"

    @pytest.mark.parametrize("keys", [["lr"], ["lr", "grad_norm", "epoch_time"], []])
    def test_a_rate_or_a_timing_is_not_a_score(self, keys: list[str]) -> None:
        assert story_metric(TaskType.CUSTOM, keys) is None

    def test_a_task_s_own_list_is_untouched(self) -> None:
        assert story_metric(TaskType.CLASSIFICATION, ["recall", "val_accuracy"]) == "val_accuracy"
        assert story_metric(TaskType.CLASSIFICATION, ["recall"]) is None


class TestTheStory:
    def test_precision_and_recall_alone_are_told(self, tmp_path: Path) -> None:
        run, frames = _told(tmp_path, _lines("Epoch {e}/5 precision={p} recall={r}"))
        assert run.task_type is TaskType.CUSTOM
        assert [f.primary_metric for f in frames] == ["precision"] * 5
        assert [f.primary_metric_value for f in frames] == PRECISION
        # No scale of its own: the letter is how far it moved.
        assert frames[-1].grade is grade_by_trajectory(PRECISION[0], PRECISION[-1], False)

    def test_recall_alone_is_told(self, tmp_path: Path) -> None:
        _, frames = _told(tmp_path, [f"Epoch {e}/5 recall={r}" for e, r in enumerate(RECALL, 1)])
        assert [f.primary_metric_value for f in frames] == RECALL
        assert {f.primary_metric for f in frames} == {"recall"}

    def test_a_learning_rate_alone_is_still_no_story(self, tmp_path: Path) -> None:
        _, frames = _told(tmp_path, [f"Epoch {e}/5 lr={0.01 / e:.5f}" for e in range(1, 6)])
        assert frames == []

    def test_a_lightning_setting_does_not_become_the_story(self, tmp_path: Path) -> None:
        lines = ["precision=16 batch_size=32", *_lines("Epoch {e}/5 train_loss={r} recall={p}")]
        _, frames = _told(tmp_path, lines)
        assert {f.primary_metric for f in frames} == {"train_loss"}
        assert len(frames) == 5


class TestCheck:
    def test_it_names_the_metric_the_run_is_told_by(self, tmp_path: Path) -> None:
        out = _check(tmp_path, _lines("Epoch {e}/5 precision={p} recall={r}"))
        assert "precision" in out and "recall" in out
        assert "told by precision" in out
        assert "its loss" not in out, "the log has no loss"

    def test_a_loss_only_run_is_told_by_its_loss(self, tmp_path: Path) -> None:
        out = _check(tmp_path, [f"Epoch {e}/5 train_loss={1 / e:.3f}" for e in range(1, 6)])
        assert "No task-defining metric" in out
        assert "told by train_loss" in out

    def test_it_does_not_promise_a_fixed_scale_for_a_metric_graded_on_improvement(
        self, tmp_path: Path
    ) -> None:
        """The hint named F1 and MAE as the way to "a real grade"."""
        out = _check(tmp_path, [f"Epoch {e}/5 train_loss={1 / e:.3f}" for e in range(1, 6)])
        hint = out[out.index("No task-defining metric") :].split(")")[0]
        assert "F1" not in hint and "MAE" not in hint, hint

    def test_a_log_with_nothing_to_tell_says_so(self, tmp_path: Path) -> None:
        out = _check(tmp_path, [f"Epoch {e}/5 lr={0.01 / e:.5f}" for e in range(1, 6)])
        assert "Nothing in this log can carry a story: lr is not a score." in out
        assert "graded on" not in out
