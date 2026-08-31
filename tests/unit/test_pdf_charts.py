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
    tmp_path: Path, series: dict[str, list[float]], *, epochs: bool = True
) -> tuple[str, RunStore]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = RunStore(str(tmp_path / "c.db"))
    run_id = "01PDFCHARTRUN"
    store.create_run(
        Run(
            id=run_id,
            name="chart run",
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
                primary_metric_value=series.get("val_accuracy", [0.5])[min(i, 0)],
                narrative=f"Epoch {i + 1}.",
                progress=0.5,
                confidence=0.8,
                task_type=TaskType.CLASSIFICATION,
            )
        )
    store.finish_run(run_id, final_grade=Grade.B, story_summary="Done.")
    return run_id, store


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
        run_id, store = _store(tmp_path, {"custom": [1.0, 2.0, 3.0]})
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
