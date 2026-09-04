"""A run whose loss becomes NaN must not be reported as a healthy run.

`loss: nan` is the plainest failure signal a training log has, and it was
invisible end to end. Two silent layers:

1. The parsers' shared number pattern requires a digit, so the token `nan`
   matched nothing and no RawMetric was produced for those lines.
2. `MetricEvent.value` is a ``FiniteFloat`` — deliberately, because it is what
   keeps ``--json`` and the embedded HTML run data valid (``NaN`` is not legal
   JSON) — so even a non-finite RawMetric would be dropped by `normalize()`
   inside a bare ``except ValueError: continue``.

The result: a model whose loss went to NaN at epoch 4 was reported as
**Grade: B+**, *"the model makes steady progress"*, with zero warnings and a
story that simply stopped at epoch 3.

The engine had the vocabulary for this all along (`impossible_reason` returns
"is not a number (NaN) — usually a diverged loss"; `WarningDetector` has an
`isnan` branch) — none of it reachable from a parsed log.
"""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING

from epochix import parse
from epochix.enums import Grade
from epochix.models import Run, StoryFrame
from epochix.pipeline import _NON_FINITE_ASSIGNMENT

if TYPE_CHECKING:
    from pathlib import Path

_DIVERGED_LOG = [
    "Epoch 1/6 - loss: 0.9000 - val_loss: 0.9500",
    "Epoch 2/6 - loss: 0.7000 - val_loss: 0.7600",
    "Epoch 3/6 - loss: 0.5000 - val_loss: 0.5900",
    "Epoch 4/6 - loss: nan - val_loss: nan",
    "Epoch 5/6 - loss: nan - val_loss: nan",
    "Epoch 6/6 - loss: nan - val_loss: nan",
]


def _story(
    tmp_path: Path, lines: list[str], name: str = "t", locale: str = "en"
) -> tuple[Run, list[StoryFrame]]:
    from epochix.store.sqlite_store import RunStore

    log = tmp_path / f"{name}.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    db = str(tmp_path / f"{name}.db")
    run = parse(log, db=db, run_name=name, locale=locale)
    return run, RunStore(db_path=db).get_story_frames(run.id)


class TestADivergedRunSaysSo:
    def test_the_grade_is_not_the_one_it_earned_before_blowing_up(self, tmp_path: Path) -> None:
        run, _frames = _story(tmp_path, _DIVERGED_LOG, "div")
        assert run.final_grade == Grade.F, (
            f"a run whose loss became NaN was graded {run.final_grade}"
        )

    def test_the_summary_names_the_divergence(self, tmp_path: Path) -> None:
        run, _frames = _story(tmp_path, _DIVERGED_LOG, "div")
        summary = (run.story_summary or "").lower()
        assert "diverg" in summary or "not a number" in summary or "nan" in summary, (
            f"the run summary never mentions the divergence: {run.story_summary!r}"
        )
        assert "steady progress" not in summary, run.story_summary

    def test_a_divergence_warning_is_emitted(self, tmp_path: Path) -> None:
        _run, frames = _story(tmp_path, _DIVERGED_LOG, "div")
        kinds = {w.kind for f in frames for w in f.warnings}
        assert "divergence" in kinds, f"no divergence warning; got {kinds}"

    def test_the_narrative_quotes_the_last_real_reading(self, tmp_path: Path) -> None:
        """No invented number: the last usable value was 0.5900 at epoch 3."""
        run, _frames = _story(tmp_path, _DIVERGED_LOG, "div")
        assert "0.5900" in (run.story_summary or ""), run.story_summary

    def test_no_frame_claims_a_reading_after_the_last_finite_epoch(self, tmp_path: Path) -> None:
        """The chart must not gain a flat segment invented from thin air."""
        _run, frames = _story(tmp_path, _DIVERGED_LOG, "div")
        epochs = [f.epoch for f in frames if f.epoch is not None]
        assert max(epochs) <= 3.0, f"a frame was dated past the last real reading: {epochs}"

    def test_it_is_localised(self, tmp_path: Path) -> None:
        run, _frames = _story(tmp_path, _DIVERGED_LOG, "div_fa", locale="fa")
        assert re.search(r"[؀-ۿ]", run.story_summary or ""), run.story_summary


def _non_finite_paths(obj: object, path: str = "") -> list[str]:
    """Every place a non-finite float sits in a nested payload."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found += _non_finite_paths(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _non_finite_paths(v, f"{path}[{i}]")
    elif isinstance(obj, float) and not math.isfinite(obj):
        found.append(f"{path}={obj!r}")
    return found


class TestSerialisationStaysValid:
    """`json.dumps(float("nan"))` emits a bare ``NaN``, which no JSON parser
    accepts. That is exactly why ``MetricEvent.value`` is a ``FiniteFloat``, and
    why the divergence signal must not travel as a metric value.

    Checked structurally rather than by scanning the text: the word "NaN"
    legitimately appears inside the narrative ("became undefined (NaN)"), where
    it is just a character in a quoted string. A regex over the serialised text
    cannot tell the two apart — and since the narrative variant is chosen by a
    hash of the run id, such a test fails only for some runs.
    """

    def test_no_non_finite_float_reaches_the_payload(self, tmp_path: Path) -> None:
        run, frames = _story(tmp_path, _DIVERGED_LOG, "div")
        payload = {
            "run": run.model_dump(mode="json"),
            "frames": [f.model_dump(mode="json") for f in frames],
        }
        assert _non_finite_paths(payload) == []

    def test_the_payload_round_trips_through_a_strict_parser(self, tmp_path: Path) -> None:
        """`parse_constant` fires on exactly the bare NaN/Infinity tokens."""
        run, frames = _story(tmp_path, _DIVERGED_LOG, "div")
        text = json.dumps(
            {
                "run": run.model_dump(mode="json"),
                "frames": [f.model_dump(mode="json") for f in frames],
            }
        )

        def reject(token: str) -> object:
            raise AssertionError(f"bare {token} token in the serialised payload")

        json.loads(text, parse_constant=reject)


class TestTheSentinelDoesNotMisreadProse:
    """Inventing a divergence is worse than missing one.

    The pattern requires an explicit `:` or `=`, which is what keeps it off
    ordinary log prose. It is kept out of the parsers' shared `_NUM` for this
    reason: `_NUM` feeds bare `key value` patterns that would then read words.
    """

    def test_it_matches_real_assignments(self) -> None:
        for line in ("loss: nan", "val_loss=inf", "loss = -inf", "Loss: NaN", "x=infinity"):
            assert _NON_FINITE_ASSIGNMENT.search(line), f"missed {line!r}"

    def test_it_ignores_prose_and_identifiers(self) -> None:
        for line in (
            "Namespace(infer=True)",
            "info: starting run",
            "Training on inf batches",
            "nan_policy='omit'",
            "INFO: dataset shape (60000, 28, 28)",
            "loss: 0.4",
            "to infinity and beyond",
        ):
            assert not _NON_FINITE_ASSIGNMENT.search(line), f"false positive on {line!r}"

    def test_a_healthy_log_mentioning_inf_is_not_marked_diverged(self, tmp_path: Path) -> None:
        lines = [
            "Namespace(lr=0.001, infer=True, nan_policy='omit')",
            "Loaded 512 inference batches; info: starting run",
            "Epoch 1/3 - loss: 0.9000 - val_accuracy: 0.6100",
            "Epoch 2/3 - loss: 0.7000 - val_accuracy: 0.6800",
            "Epoch 3/3 - loss: 0.5000 - val_accuracy: 0.7400",
        ]
        run, frames = _story(tmp_path, lines, "clean")
        assert run.final_grade != Grade.F, "a healthy run was marked diverged"
        kinds = {w.kind for f in frames for w in f.warnings}
        assert "divergence" not in kinds, kinds


class TestTheSdkTakesTheSamePath:
    """`LiveReporter.log(**metrics)` does not hand the engine floats.

    It renders each kwarg as ``f"{k}={v}"`` and pushes the resulting line
    through the very same parsers a log file goes through. So the divergence
    sentinel is what covers the SDK too — and it only does so because
    ``str(float("nan"))`` is exactly ``"nan"``. If that formatting ever changed
    (to ``"NaN"``, or to dropping the key), the SDK would go quiet again.
    """

    def test_a_nan_metric_renders_in_a_form_the_sentinel_catches(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            line = "  ".join(f"{k}={v}" for k, v in {"train_loss": value}.items())
            assert _NON_FINITE_ASSIGNMENT.search(line), (
                f"LiveReporter would emit {line!r}, which the sentinel misses"
            )

    def test_a_finite_metric_does_not_trip_it(self) -> None:
        line = "  ".join(f"{k}={v}" for k, v in {"epoch": 4, "train_loss": 0.5}.items())
        assert not _NON_FINITE_ASSIGNMENT.search(line), line
