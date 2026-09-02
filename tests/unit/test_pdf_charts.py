"""The PDF has to show the curve, not just describe it.

A 20-epoch export was five pages carrying four lines of text each and not one
graphic — roughly 85% of every landscape page blank — while the run had 44
metric events across four series sitting unused in the store. For a product
whose whole claim is that the *shape* of a run is the story, a report with no
shape in it is the wrong artifact.

Charts are drawn with fpdf2's own line primitives, so this costs no dependency.
"""

from __future__ import annotations

import re
import zlib
from datetime import datetime, timezone
from pathlib import Path

from epochix.enums import Grade, Phase, TaskType
from epochix.exporters.pdf_export import build_pdf
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.store.sqlite_store import RunStore

CHART_TITLE = "How the run moved"


def _store(
    tmp_path: Path,
    series: dict[str, list[float]],
    *,
    epochs: bool = True,
    name: str = "chart run",
    skills: dict[str, float] | None = None,
) -> tuple[str, RunStore]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = RunStore(str(tmp_path / "c.db"))
    run_id = "01PDFCHARTRUN"
    store.create_run(
        Run(
            id=run_id,
            name=name,
            task_type=TaskType.CLASSIFICATION,
            started_at=datetime.now(tz=timezone.utc),
            primary_metric="val_accuracy",
            parser_used="test",
        )
    )
    seq = 0
    length = max(len(v) for v in series.values())
    for i in range(length):
        for key, values in series.items():
            if i >= len(values):
                continue
            seq += 1
            store.append_metric_event(
                MetricEvent(
                    run_id=run_id,
                    seq=seq,
                    timestamp=datetime.now(tz=timezone.utc),
                    epoch=float(i + 1) if epochs else None,
                    canonical_key=key,
                    raw_key=key,
                    value=values[i],
                )
            )
        store.append_story_frame(
            StoryFrame(
                run_id=run_id,
                seq=seq,
                epoch=float(i + 1) if epochs else None,
                phase=Phase.LEARNING,
                grade=Grade.B,
                primary_metric="val_accuracy",
                primary_metric_value=_frame_value(series, i),
                narrative=f"Epoch {i + 1}.",
                progress=0.5,
                confidence=0.8,
                task_type=TaskType.CLASSIFICATION,
                skill_dimensions=skills or {},
            )
        )
    store.finish_run(run_id, final_grade=Grade.B, story_summary="Done.")
    return run_id, store


def _frame_value(series: dict[str, list[float]], i: int) -> float:
    """The i-th reading of the frame's own metric.

    This used to be `[min(i, 0)]`, which is always index 0 — every frame in the
    fixture carried the FIRST value, so any assertion about a run changing over
    time passed against a flat series that never moved.
    """
    values = series.get("val_accuracy") or next(iter(series.values()))
    return values[min(i, len(values) - 1)]


def _pdf_text(pdf: bytes) -> str:
    blob = ""
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            blob += zlib.decompress(m.group(1)).decode("latin-1")
        except zlib.error:
            continue
    return blob


def _drawn_lines(pdf: bytes) -> int:
    """Count stroked path segments — the curve itself, not its label."""
    return len(re.findall(r"\bl\s", _pdf_text(pdf)))


class TestTheCurveIsDrawn:
    def test_a_multi_epoch_run_gets_a_charts_page(self, tmp_path: Path) -> None:
        run_id, store = _store(
            tmp_path,
            {
                "train_loss": [1.8, 1.2, 0.9, 0.7, 0.6],
                "val_loss": [1.7, 1.3, 1.0, 0.9, 0.85],
                "accuracy": [0.32, 0.51, 0.63, 0.71, 0.79],
            },
        )
        pdf = build_pdf(run_id=run_id, store=store)
        assert CHART_TITLE in _pdf_text(pdf)

    def test_it_actually_strokes_lines(self, tmp_path: Path) -> None:
        """The page title alone would pass while drawing nothing.

        Measured against the same run with an unchartable metric rather than a
        guessed threshold: the difference is exactly what the charts drew.
        """
        charted, store_a = _store(
            tmp_path / "a",
            {"train_loss": [1.8, 1.2, 0.9, 0.7, 0.6], "accuracy": [0.3, 0.5, 0.6, 0.7, 0.8]},
        )
        plain, store_b = _store(tmp_path / "b", {"custom": [1.0, 2.0, 3.0, 4.0, 5.0]})

        with_charts = _drawn_lines(build_pdf(run_id=charted, store=store_a))
        without = _drawn_lines(build_pdf(run_id=plain, store=store_b))
        assert with_charts > without, (with_charts, without)

    def test_both_series_are_labelled(self, tmp_path: Path) -> None:
        """Two curves with no legend is a picture you cannot read."""
        run_id, store = _store(
            tmp_path, {"train_loss": [1.8, 1.2, 0.9], "val_loss": [1.7, 1.3, 1.1]}
        )
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "train_loss" in text
        assert "val_loss" in text

    def test_loss_and_accuracy_are_not_on_one_axis(self, tmp_path: Path) -> None:
        """They share no scale: an accuracy of 0.8 beside a loss of 1.8 would
        flatten one of them against the axis and imply it never moved."""
        run_id, store = _store(
            tmp_path, {"train_loss": [1.8, 1.2, 0.9], "accuracy": [0.3, 0.5, 0.8]}
        )
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "Loss" in text
        assert "Quality" in text


class TestItDoesNotInventShape:
    def test_a_run_with_no_chartable_metric_gets_no_chart_page(self, tmp_path: Path) -> None:
        """`lr` is a real metric that belongs to no chart group.

        This used to use `custom`, which was the right example until `custom`
        was deliberately given its own panel — a GridSearchCV score
        canonicalises to it and was reaching no curve at all. A learning rate
        is the honest remaining case: charted nowhere, and not a mistake.
        """
        run_id, store = _store(tmp_path, {"lr": [0.01, 0.005, 0.001]})
        assert CHART_TITLE not in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_a_single_reading_is_a_point_not_a_trend(self, tmp_path: Path) -> None:
        """One measurement cannot describe a direction, so no segment is drawn
        between it and anything else."""
        run_id, store = _store(tmp_path, {"accuracy": [0.98]})
        pdf = build_pdf(run_id=run_id, store=store)
        assert pdf.startswith(b"%PDF-")

    def test_a_run_without_epochs_still_charts(self, tmp_path: Path) -> None:
        """Boosting rounds and bare `iter` counters are a real ordering."""
        run_id, store = _store(
            tmp_path,
            {"log_loss": [0.52, 0.40, 0.31, 0.25], "val_log_loss": [0.53, 0.42, 0.34, 0.29]},
            epochs=False,
        )
        assert CHART_TITLE in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_a_flat_series_does_not_divide_by_zero(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"accuracy": [0.5, 0.5, 0.5, 0.5]})
        assert build_pdf(run_id=run_id, store=store).startswith(b"%PDF-")


class TestTheCoverSupportsItsGrade:
    """A grade is the loudest claim in the document and had nothing behind it.

    The cover carried a letter, a run id, a task, a date and one sentence — no
    best epoch, no final value, no epoch count, nothing a reader could check
    the letter against.
    """

    def test_best_and_final_are_both_stated(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.30, 0.55, 0.80, 0.72]})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "final val_accuracy" in text
        assert "best val_accuracy" in text

    def test_drift_from_best_says_which_way(self, tmp_path: Path) -> None:
        """A run that peaked and fell back. The sign alone is ambiguous: on a
        loss, +0.002 is the model getting worse."""
        run_id, store = _store(tmp_path, {"val_accuracy": [0.30, 0.55, 0.80, 0.72]})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "since best" in text
        assert "worse" in text

    def test_a_run_still_at_its_best_reports_no_drift(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.30, 0.55, 0.72, 0.80]})
        assert "since best" not in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_the_epoch_span_is_stated(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.5, 0.7]})
        assert "epochs" in _pdf_text(build_pdf(run_id=run_id, store=store))


class TestEveryEpochIsListed:
    """One page per phase rendered 3 pages for an 11-frame run — eight
    readings absent from the report, including whichever was the best."""

    def test_all_epochs_appear(self, tmp_path: Path) -> None:
        values = [0.30, 0.42, 0.55, 0.61, 0.68, 0.72]
        run_id, store = _store(tmp_path, {"val_accuracy": values})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "Every epoch" in text
        for v in values:
            assert f"{v:.4g}" in text, v

    def test_the_best_row_is_marked(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.30, 0.80, 0.55]})
        assert "best" in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_a_single_reading_gets_no_table(self, tmp_path: Path) -> None:
        """Two rows is the minimum for a table to say anything."""
        run_id, store = _store(tmp_path, {"val_accuracy": [0.98]})
        assert "Every epoch" not in _pdf_text(build_pdf(run_id=run_id, store=store))


class TestALongRunStaysReadable:
    """A 40-round boosting run overflows one page.

    The continuation used to open on a bare data row — five unlabelled columns
    of numbers, with the title and headers left behind on the previous sheet.
    """

    def test_the_header_repeats_after_a_page_break(self, tmp_path: Path) -> None:
        values = [1.0 - i * 0.02 for i in range(45)]
        run_id, store = _store(tmp_path, {"val_accuracy": values})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        # Parentheses are backslash-escaped inside a PDF string literal, so
        # match the word rather than the exact phrase.
        assert "continued" in text
        # The column headers appear once per page, so more than once overall.
        assert text.count("change") >= 2, text.count("change")

    def test_a_short_run_has_no_continuation(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.5, 0.7]})
        assert "continued" not in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_a_long_name_is_truncated(self, tmp_path: Path) -> None:
        """120 characters ran off both edges of the cover."""
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.6]}, name="y" * 120)
        pdf = build_pdf(run_id=run_id, store=store)
        text = _pdf_text(pdf)
        assert "y" * 120 not in text
        assert "y" * 40 in text  # the name is still recognisable

    def test_truncation_uses_characters_the_font_has(self, tmp_path: Path) -> None:
        """The marker must be Latin-1. A U+2026 ellipsis raised
        FPDFUnicodeEncodingException and took the whole export down — a crash
        on every over-long name, introduced by the truncation itself."""
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.6]}, name="z" * 200)
        assert build_pdf(run_id=run_id, store=store).startswith(b"%PDF-")


class TestTheFinalMetricsTable:
    """It was a bare list: four numbers with nothing to compare them against."""

    def test_every_series_gets_a_best_and_a_change(self, tmp_path: Path) -> None:
        run_id, store = _store(
            tmp_path,
            {"val_accuracy": [0.30, 0.55, 0.80], "train_loss": [1.8, 1.1, 0.7]},
        )
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "val_accuracy" in text and "train_loss" in text
        assert "+0.5" in text  # accuracy climbed
        assert "-1.1" in text  # loss fell

    def test_best_respects_the_metric_direction(self, tmp_path: Path) -> None:
        """A loss is at its best when lowest. Reporting its maximum would call
        the worst epoch the best one.

        The whole cell is asserted, not just the number: "0.4" also appears in
        the epoch table, so a substring check passed whichever direction the
        code used and proved nothing.
        """
        run_id, store = _store(tmp_path, {"train_loss": [1.8, 0.4321, 0.9]})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        # Parentheses are backslash-escaped inside a PDF string literal.
        assert r"0.4321 \(epoch 2\)" in text, "best should be the lowest loss"
        assert r"1.8 \(epoch 1\)" not in text.split("Final metrics")[-1]

    def test_a_single_reading_shows_no_change(self, tmp_path: Path) -> None:
        """One measurement has not changed by zero — it has not changed."""
        run_id, store = _store(tmp_path, {"val_accuracy": [0.98]})
        assert "+0" not in _pdf_text(build_pdf(run_id=run_id, store=store))


class TestSkillsAndModelReachTheDocument:
    """The engine scores four dimensions per frame and the log's model summary
    is parsed into real layers. Neither had ever left the dashboard."""

    def test_skill_bars_are_drawn(self, tmp_path: Path) -> None:
        run_id, store = _store(
            tmp_path,
            {"val_accuracy": [0.3, 0.6, 0.8]},
            skills={"Accuracy": 0.79, "Generalisation": 0.92},
        )
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "Skills" in text
        assert "Generalisation" in text

    def test_a_run_without_skills_omits_the_section(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.6]})
        assert "Skills" not in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_the_architecture_is_listed_with_its_total(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.6]})
        store.update_run_config(
            run_id,
            {
                "architecture": [
                    {
                        "name": "conv2d",
                        "layer_type": "Conv2D",
                        "params": 896,
                        "params_str": "896",
                        "plain_label": "Spatial patterns",
                    },
                    {
                        "name": "dense",
                        "layer_type": "Dense",
                        "params": 650,
                        "params_str": "650",
                        "plain_label": "Decision maker",
                    },
                ]
            },
        )
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "conv2d" in text and "Conv2D" in text
        assert "1,546" in text  # 896 + 650, counted over every layer

    def test_a_run_without_an_architecture_omits_the_section(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.3, 0.6]})
        assert "The model" not in _pdf_text(build_pdf(run_id=run_id, store=store))


class TestPhasePagesCoverTheirSpan:
    """A phase page showed the first frame and nothing else — four lines, with
    no sign that one phase lasted four epochs and another six."""

    def test_a_multi_epoch_phase_reports_its_range(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.30, 0.45, 0.60, 0.72]})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "epochs" in text

    def test_it_reports_what_the_metric_did(self, tmp_path: Path) -> None:
        run_id, store = _store(tmp_path, {"val_accuracy": [0.30, 0.45, 0.60, 0.72]})
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "->" in text


class TestTheLastTwoGaps:
    """The two items the PDF roadmap still carried."""

    def test_an_unrecognised_series_still_gets_a_curve(self, tmp_path: Path) -> None:
        """A GridSearchCV score canonicalises to `custom`, which belonged to no
        chart group — so the only number the search produced never reached a
        curve, on a page titled "How the run moved"."""
        run_id, store = _store(tmp_path, {"custom": [0.92, 0.94, 0.95, 0.96]})
        assert CHART_TITLE in _pdf_text(build_pdf(run_id=run_id, store=store))

    def test_a_deep_model_lists_every_layer(self, tmp_path: Path) -> None:
        """The layer table ran to the page edge and stopped, reporting the rest
        as a count. A model is not described by its first twenty layers."""
        run_id, store = _store(
            tmp_path, {"val_accuracy": [0.3, 0.6, 0.8]}, skills={"Accuracy": 0.8}
        )
        store.update_run_config(
            run_id,
            {
                "architecture": [
                    {
                        "name": f"layer_{i}",
                        "layer_type": "Dense",
                        "params": 100 + i,
                        "params_str": str(100 + i),
                        "plain_label": "Decision maker",
                    }
                    for i in range(60)
                ]
            },
        )
        text = _pdf_text(build_pdf(run_id=run_id, store=store))
        assert "layer_0" in text
        assert "layer_59" in text, "the deepest layers were dropped at the page edge"
        assert "continued" in text
