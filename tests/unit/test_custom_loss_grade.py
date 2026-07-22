"""CUSTOM / loss-only runs must be graded sensibly, not scored as accuracy.

A script that logs only a loss curve (no accuracy) detects as CUSTOM. CUSTOM had
no grade thresholds, so compute_grade fell back to the CLASSIFICATION scale
(higher-is-better accuracy) — and a healthy validation loss of 0.19 was graded
as if it were 19% accuracy → F, contradicting the "trend is positive" narrative.

CUSTOM metrics have no absolute scale, so they're now graded on improvement
from baseline instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from epochix.enums import Grade
from epochix.story_engine.grade import (
    grade_by_trajectory,
    metric_lower_better,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestMetricDirection:
    def test_loss_names_are_lower_better(self) -> None:
        for name in ("val_loss", "loss", "train_loss", "rmse", "mae", "eer", "perplexity"):
            assert metric_lower_better(name) is True, name

    def test_score_names_are_higher_better(self) -> None:
        for name in ("val_accuracy", "accuracy", "f1", "auc", "map50", "precision"):
            assert metric_lower_better(name) is False, name

    def test_unknown_names_return_none(self) -> None:
        assert metric_lower_better("widget_score") is None
        assert metric_lower_better(None) is None


class TestTrajectoryGrade:
    def test_big_loss_reduction_earns_a_top_grade(self) -> None:
        # 0.49 → 0.19 is a ~61% reduction — a model training well.
        assert grade_by_trajectory(0.49, 0.19, lower_better=True) in {Grade.A, Grade.A_PLUS}

    def test_small_loss_reduction_earns_a_middling_grade(self) -> None:
        # The friend's run: 0.212 → 0.189, ~11% — mediocre, but NOT F.
        g = grade_by_trajectory(0.212, 0.189, lower_better=True)
        assert g not in {Grade.F, Grade.D}, g
        assert g in {Grade.C_PLUS, Grade.C, Grade.B_MINUS}, g

    def test_diverging_loss_is_a_failing_grade(self) -> None:
        # 0.36 → 0.66 got worse — that genuinely deserves F.
        assert grade_by_trajectory(0.36, 0.66, lower_better=True) is Grade.F

    def test_higher_is_better_direction(self) -> None:
        # A custom score that climbed a lot.
        assert grade_by_trajectory(0.40, 0.90, lower_better=False) in {Grade.A, Grade.A_PLUS}
        # …and one that fell.
        assert grade_by_trajectory(0.90, 0.40, lower_better=False) is Grade.F


def _grade_run(tmp_path: Path, lines: list[str]) -> tuple[str, str, str]:
    from epochix import parse

    log = tmp_path / "run.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run = parse(log, db=str(tmp_path / "runs.db"), run_name="t")
    return run.task_type.value, run.primary_metric or "", run.final_grade.value


def test_loss_only_healthy_run_is_not_f(tmp_path: Path) -> None:
    lines = ["device=cpu epochs=6"]
    for e in range(1, 7):
        lines.append(f"Epoch {e}/6 train_loss={0.6 - e * 0.07:.4f} val_loss={0.55 - e * 0.06:.4f}")
    task, primary, grade = _grade_run(tmp_path, lines)
    assert task == "custom"
    assert "loss" in primary
    assert grade not in {"F", "D"}, f"a decreasing val_loss was graded {grade}"


def test_loss_only_diverging_run_is_poor(tmp_path: Path) -> None:
    lines = ["device=cpu epochs=6"]
    for e in range(1, 7):
        lines.append(f"Epoch {e}/6 train_loss={0.3 + e * 0.05:.4f} val_loss={0.3 + e * 0.06:.4f}")
    _, _, grade = _grade_run(tmp_path, lines)
    assert grade in {"F", "D", "C-"}, f"a diverging loss should grade poorly, got {grade}"
