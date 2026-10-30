"""A frame replayed after the warm-up reads the history of its own reading.

The engine buffers its first events until it can classify the task, then builds
their frames all at once. Those frames read the metric history, which by then
held the later readings too, so the detector was handed the newest loss for every
one of them: 0.5, 500, 400, 300 never showed it the 0.5, and no divergence was
reported. The extension's engine, which has no warm-up, did report it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from epochix import parse
from epochix.enums import Grade
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.warnings import WarningDetector

if TYPE_CHECKING:
    from epochix.models import StoryFrame, Warning


REPO = Path(__file__).parents[2]


def _story(tmp_path: Path, lines: list[str]) -> list[StoryFrame]:
    log = tmp_path / "t.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / "t.db")
    run = parse(log, db=db, run_name="t")
    return RunStore(db_path=db).get_story_frames(run.id)


def _handed_to_the_detector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, lines: list[str]
) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    update = WarningDetector.update

    def spy(
        self: WarningDetector,
        epoch: float | None,
        *args: float | None,
        **kwargs: Any,  # noqa: ANN401
    ) -> list[Warning]:
        seen.append({"epoch": epoch, **kwargs})
        return update(self, epoch, *args, **kwargs)

    monkeypatch.setattr(WarningDetector, "update", spy)
    _story(tmp_path, lines)
    return seen


def _kinds(frames: list[StoryFrame]) -> list[tuple[float | None, str]]:
    return [(f.epoch, w.kind) for f in frames for w in f.warnings]


class TestTheDetectorSeesEachReading:
    def test_each_frame_passes_the_values_of_its_own_line(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        lines = [
            "[Epoch 1/4] train_loss=0.5 val_loss=0.9 lr=0.1",
            "[Epoch 2/4] train_loss=0.4 val_loss=0.8 lr=0.09",
            "[Epoch 3/4] train_loss=0.3 val_loss=0.7 lr=0.08",
            "[Epoch 4/4] train_loss=0.2 val_loss=0.6 lr=0.07",
        ]
        seen = _handed_to_the_detector(monkeypatch, tmp_path, lines)
        assert [s["train_loss"] for s in seen] == [0.5, 0.4, 0.3, 0.2]
        assert [s["val_loss"] for s in seen] == [0.9, 0.8, 0.7, 0.6]
        assert [s["lr"] for s in seen] == [0.1, 0.09, 0.08, 0.07]

    def test_metrics_on_separate_lines_pair_with_the_latest_before_them(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # One event a line, so the warm-up ends inside the second epoch.
        lines = [
            "[Epoch 1/3] train_loss=0.5",
            "[Epoch 1/3] val_loss=0.9",
            "[Epoch 2/3] train_loss=0.4",
            "[Epoch 2/3] val_loss=0.8",
            "[Epoch 3/3] train_loss=0.3",
            "[Epoch 3/3] val_loss=0.7",
        ]
        seen = _handed_to_the_detector(monkeypatch, tmp_path, lines)
        assert [(s["train_loss"], s["val_loss"]) for s in seen] == [
            (0.5, 0.9),
            (0.4, 0.8),
            (0.3, 0.7),
        ]


class TestWhatTheRunReports:
    def test_a_blow_up_at_the_second_reading_is_reported(self, tmp_path: Path) -> None:
        lines = [
            f"Epoch {e}/4 - loss: {v:.4f} - val_loss: {0.9 - e * 0.01:.4f}"
            for e, v in enumerate([0.5, 500.0, 400.0, 300.0], start=1)
        ]
        assert _kinds(_story(tmp_path, lines))[0] == (2.0, "divergence")

    def test_a_learning_rate_drop_in_the_warm_up_is_dated_to_its_reading(
        self, tmp_path: Path
    ) -> None:
        lines = [
            "[Epoch 1/4] val_loss=0.9 lr=0.1",
            "[Epoch 2/4] val_loss=0.8 lr=0.01",
            "[Epoch 3/4] val_loss=0.7 lr=0.01",
            "[Epoch 4/4] val_loss=0.6 lr=0.01",
        ]
        assert _kinds(_story(tmp_path, lines)) == [(2.0, "lr_drop")]

    @pytest.mark.parametrize(
        "log",
        [
            "demo/huggingface_bert.log",
            "tests/fixtures/logs/catboost_real_classifier.log",
            "tests/fixtures/logs/catboost_real_no_eval_set.log",
            "tests/fixtures/logs/catboost_real_regressor.log",
            "tests/fixtures/logs/catboost_real_two_eval_sets.log",
            "tests/fixtures/logs/multiline_json.log",
        ],
    )
    def test_one_reading_is_not_graded_on_improvement(self, tmp_path: Path, log: str) -> None:
        """These recorded and sample runs opened on a D "on improvement" from one
        reading, because the readings the warm-up buffered counted as already seen."""
        db = str(tmp_path / "t.db")
        run = parse(REPO / log, db=db, run_name="t")
        first = RunStore(db_path=db).get_story_frames(run.id)[0]
        assert first.grade == Grade.INCOMPLETE
        assert first.grade_basis is None

    def test_the_first_frame_s_skills_are_its_own_reading(self, tmp_path: Path) -> None:
        lines = [f"[Epoch {e}/5] val_accuracy={0.5 + e * 0.05:.2f}" for e in range(1, 6)]
        frames = _story(tmp_path, lines)
        assert frames[0].skill_dimensions["Val Accuracy"] == pytest.approx(0.55)


class TestTheEngineStillReadsEverything:
    def test_the_replay_leaves_the_full_history_behind(self, tmp_path: Path) -> None:
        lines = [
            f"[Epoch {e}/5] train_loss={1 - e * 0.1:.1f} val_loss={1 - e * 0.05:.2f}"
            for e in range(1, 6)
        ]
        frames = _story(tmp_path, lines)
        assert len(frames) == 5
        assert frames[-1].primary_metric == "val_loss"
        assert frames[-1].primary_metric_value == pytest.approx(0.75)

    def test_the_story_metric_is_not_chosen_from_a_truncated_history(self, tmp_path: Path) -> None:
        # val_accuracy only appears on the third line, after the warm-up began.
        # The replay must not tell the earlier val_loss readings as the story.
        lines = [
            "[Epoch 1/3] val_loss=0.9",
            "[Epoch 2/3] val_loss=0.8",
            "[Epoch 3/3] val_loss=0.7 val_accuracy=0.8",
        ]
        frames = _story(tmp_path, lines)
        assert frames, "the run produced no story"
        assert {f.primary_metric for f in frames} == {"val_accuracy"}
