"""The story must not name a metric the run never logged, or grade one backwards.

Every failure here was found by reading rendered output, not by the suite:

* An XGBoost run (task classification, primary ``val_log_loss``) was narrated
  "Accuracy 41.8%" — a log loss relabelled as an accuracy and multiplied by 100.
* A segmentation run logging ``Dice`` was narrated "IoU 0.8900". Dice and IoU
  are different numbers.
* A summariser logging ROUGE was graded **F** and told "past its best ...
  stopping earlier would have been better" while its ROUGE was *rising*, then
  narrated "Perplexity falls to 0.5000" — wrong metric and wrong direction.
* A YOLO log of ``box_loss``/``cls_loss`` produced no frames, no grade and
  exit 0: the names that *detected* the task could not be read as its metric.
* A past-peak loss run read "1.7300, below the best of 0.6878" — the opposite
  of what the two numbers show.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from epochix import parse
from epochix.enums import TaskType
from epochix.story_engine import _PREFERRED_KEYS_FOR_TASK
from epochix.story_engine.grade import _LOWER_BETTER, metric_lower_better
from epochix.story_engine.narrator import narrate_past_peak
from epochix.story_engine.task_classifier import _TASK_SIGNALS

if TYPE_CHECKING:
    from pathlib import Path


def _story(tmp_path: Path, lines: list[str], name: str = "t") -> tuple[object, list]:
    from epochix.store.sqlite_store import RunStore

    log = tmp_path / f"{name}.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / f"{name}.db")
    run = parse(log, db=db, run_name=name)
    return run, RunStore(db_path=db).get_story_frames(run.id)


class TestEveryTriggerKeyCanTellAStory:
    """A key that classifies a run must also be readable as its primary metric.

    Detecting the task and then having no metric to read leaves the run with no
    frames, no grade and no summary — reported to the user as "Grade: N/A" with
    a successful exit code, which is indistinguishable from a boring run.
    """

    def test_no_trigger_key_is_orphaned(self) -> None:
        orphans: dict[str, list[str]] = {}
        signals: dict[TaskType, set[str]] = {}
        for keys, task in _TASK_SIGNALS:
            signals.setdefault(task, set()).update(keys)
        for task, keys in signals.items():
            missing = sorted(keys - set(_PREFERRED_KEYS_FOR_TASK.get(task, ())))
            if missing:
                orphans[task.name] = missing
        assert orphans == {}, (
            f"these keys classify a run and then cannot be read as its metric: {orphans}"
        )

    def test_a_yolo_loss_log_tells_a_story(self, tmp_path: Path) -> None:
        """box_loss/cls_loss is what YOLO prints before mAP is ever computed."""
        lines = [
            f"Epoch {e}/10 box_loss={1.8 * 0.87**e:.4f} cls_loss={1.2 * 0.85**e:.4f}"
            for e in range(1, 11)
        ]
        run, frames = _story(tmp_path, lines, "yolo")
        assert frames, "a YOLO training log produced no story at all"
        assert run.final_grade is not None, "no grade for a run that clearly improved"


class TestMetricDirection:
    """A metric whose direction is unknown falls back to its task's default.

    That default is right for the task's headline metric and wrong for others,
    and the failure is silent: the grade simply comes out inverted.
    """

    # (metric, is-lower-better-in-reality)
    TRUTH = [
        ("rouge", False),
        ("bleu", False),
        ("meteor", False),
        ("perplexity", True),
        ("WER", True),
        ("BPC", True),
        ("fid", True),
        ("kid", True),
        ("is_score", False),
        ("PSNR", False),
        ("SSIM", False),
        ("LPIPS", True),
        ("EER", True),
        ("TAR", False),
        ("FAR", True),
        ("TAR_at_FAR_0_001", False),
        ("mAP50", False),
        ("IoU", False),
        ("Dice", False),
        ("box_loss", True),
        ("kappa", False),
        ("explained_variance", False),
        ("RMSLE", True),
        ("MedAE", True),
    ]

    @pytest.mark.parametrize(("metric", "lower_better"), TRUTH)
    def test_direction_is_known_and_correct(self, metric: str, lower_better: bool) -> None:
        assert metric_lower_better(metric) == lower_better, (
            f"{metric} direction is wrong or unpinned; an unpinned metric inherits "
            f"its task's default and inverts the grade"
        )

    def test_no_preferred_key_inherits_a_wrong_default(self) -> None:
        """Belt and braces: check the direction each task will actually use."""
        truth = dict(self.TRUTH)
        wrong = []
        for task, keys in _PREFERRED_KEYS_FOR_TASK.items():
            default = task in _LOWER_BETTER
            for key in keys:
                known = truth.get(key)
                if known is None:
                    continue
                inferred = metric_lower_better(key)
                effective = default if inferred is None else inferred
                if effective != known:
                    wrong.append(f"{task.name}/{key}")
        assert wrong == [], f"graded backwards: {wrong}"

    def test_a_rising_rouge_is_not_graded_as_decline(self, tmp_path: Path) -> None:
        lines = [
            f"Epoch {e}/10 train_loss={4.2 * 0.88**e:.4f} rouge={0.2 + 0.03 * e:.4f}"
            for e in range(1, 11)
        ]
        run, frames = _story(tmp_path, lines, "rouge")
        assert frames
        last = frames[-1].narrative.lower()
        assert "past its best" not in last, f"rising ROUGE called a decline: {last!r}"
        assert "stopping earlier" not in last, last
        assert str(run.final_grade) != "Grade.F", "an improving run graded F"


class TestProseNamesOnlyWhatWasLogged:
    """Templates that name their metric may only describe that metric."""

    def test_a_log_loss_is_not_called_accuracy(self, tmp_path: Path) -> None:
        lines = [
            f"[{i}]\ttrain-logloss:{0.68 * 0.94**i:.5f}\tvalid-logloss:{0.70 * 0.95**i + 0.02:.5f}"
            for i in range(0, 40, 5)
        ]
        run, frames = _story(tmp_path, lines, "xgb")
        assert frames
        assert run.primary_metric is not None and "loss" in run.primary_metric.lower()
        for f in frames:
            assert "accuracy" not in f.narrative.lower(), (
                f"a log loss was narrated as accuracy: {f.narrative!r}"
            )

    def test_dice_is_not_called_iou(self, tmp_path: Path) -> None:
        lines = [
            f"Epoch {e}/10 loss={1.5 * 0.86**e:.4f} val_Dice={min(0.93, 0.35 + 0.06 * e):.4f}"
            for e in range(1, 11)
        ]
        _run, frames = _story(tmp_path, lines, "seg")
        assert frames
        for f in frames:
            assert "iou" not in f.narrative.lower(), f"Dice was narrated as IoU: {f.narrative!r}"

    def test_rouge_is_not_called_perplexity(self, tmp_path: Path) -> None:
        lines = [
            f"Epoch {e}/10 train_loss={4.2 * 0.88**e:.4f} rouge={0.2 + 0.03 * e:.4f}"
            for e in range(1, 11)
        ]
        _run, frames = _story(tmp_path, lines, "nlp")
        assert frames
        for f in frames:
            assert "perplexity" not in f.narrative.lower(), (
                f"ROUGE was narrated as perplexity: {f.narrative!r}"
            )

    def test_a_real_accuracy_run_keeps_its_accuracy_prose(self, tmp_path: Path) -> None:
        """The guard must not strip good prose from the runs it was written for."""
        lines = [
            f"Epoch {e}/12 - loss: {2.3 * 0.8**e:.4f} - val_accuracy: {min(0.97, 0.4 + 0.05 * e):.4f}"
            for e in range(1, 13)
        ]
        _run, frames = _story(tmp_path, lines, "clf")
        text = " ".join(f.narrative for f in frames).lower()
        assert "accuracy" in text, "an accuracy run lost its accuracy wording"


class TestPastPeakWording:
    def test_a_loss_run_is_not_said_to_be_below_its_best(self) -> None:
        """For a loss the current value is worse by being LARGER."""
        for i in range(200):
            text = narrate_past_peak(
                epoch=20,
                primary_value=1.73,
                best_value=0.6878,
                best_epoch=6,
                run_id=f"r{i}",
                locale="en",
            )
            assert "below the best" not in text, (
                f"1.7300 is not below 0.6878: {text!r} (run id r{i})"
            )

    def test_no_variant_diagnoses_a_cause(self) -> None:
        """A diverging run was told "that is usually overfitting".

        Divergence is not overfitting and its fix is different. The overfit
        WARNING names that cause, and only with the evidence for it (validation
        loss rising while training loss falls); a single pair of numbers cannot
        tell the two apart, so the narrative must not try.
        """
        seen = set()
        for i in range(200):
            seen.add(
                narrate_past_peak(
                    epoch=8,
                    primary_value=2881.8,
                    best_value=3.588,
                    best_epoch=1,
                    run_id=f"r{i}",
                    locale="en",
                )
            )
        assert len(seen) >= 2, "expected several variants to be exercised"
        for text in seen:
            assert "overfitting" not in text.lower(), (
                f"past-peak guessed a cause the run contradicts: {text!r}"
            )

    def test_the_numbers_quoted_are_the_ones_given(self) -> None:
        text = narrate_past_peak(
            epoch=20,
            primary_value=1.73,
            best_value=0.6878,
            best_epoch=6,
            run_id="r3",
            locale="en",
        )
        assert "1.7300" in text and "0.6878" in text, text
        assert not re.search(r"\{[a-z_]+\}", text), f"unrendered token in {text!r}"
