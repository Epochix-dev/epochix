"""A Farsi run's PDF is drawn in Farsi.

fpdf2's core fonts are Latin-1, so a Farsi report fell back to English chrome
with its sentences left out. It now embeds Vazirmatn (SIL OFL, shipped with the
package) and shapes the text through uharfbuzz (`epochix[pdf]`), so letters
join and read right to left. Checked by extracting the text from the PDF, not
by trusting that a font was requested.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epochix.enums import Grade, Phase, TaskType
from epochix.exporters._pdf_render import can_draw_persian
from epochix.exporters.pdf_export import build_pdf
from epochix.i18n import t
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.store.sqlite_store import RunStore
from epochix.story_engine.messages import phase_name

pdfium = pytest.importorskip("pypdfium2")

NARRATIVE = "آموزش به پایان رسید."


def _store(tmp_path: Path) -> tuple[str, RunStore]:
    store = RunStore(str(tmp_path / "runs.db"))
    store.create_run(
        Run(
            id="fa-run",
            name="آزمایش دسته‌بندی",
            task_type=TaskType.CLASSIFICATION,
            started_at=datetime.now(tz=timezone.utc),
            primary_metric="val_accuracy",
            parser_used="keras_tensorflow",
            final_grade=Grade.B,
            story_summary=NARRATIVE,
            config={"locale": "fa"},
        )
    )
    for epoch, value in enumerate((0.5, 0.6, 0.7), start=1):
        store.append_metric_event(
            MetricEvent(
                run_id="fa-run",
                seq=epoch,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(epoch),
                canonical_key="val_accuracy",
                raw_key="val_accuracy",
                value=value,
            )
        )
        store.append_story_frame(
            StoryFrame(
                run_id="fa-run",
                seq=epoch,
                epoch=float(epoch),
                progress=epoch / 3,
                phase=Phase.LEARNING,
                grade=Grade.B,
                primary_metric_value=value,
                primary_metric="val_accuracy",
                confidence=0.5,
                narrative=NARRATIVE,
                task_type=TaskType.CLASSIFICATION,
            )
        )
    return "fa-run", store


def _words(pdf: bytes) -> set[str]:
    doc = pdfium.PdfDocument(io.BytesIO(pdf))
    text = " ".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    # Extraction drops the zero-width non-joiner and may reorder right-to-left
    # words, so compare word sets.
    return set(text.replace("‌", "").split())


def _plain(phrase: str) -> set[str]:
    return set(phrase.replace("‌", "").replace(".", "").split())


def test_this_environment_can_shape() -> None:
    """Guard: CI installs uharfbuzz (dev extra), so the tests below must run."""
    assert can_draw_persian(), "uharfbuzz or the bundled Vazirmatn font is missing"


def test_a_farsi_report_is_drawn_in_farsi(tmp_path: Path) -> None:
    run_id, store = _store(tmp_path)
    pdf = build_pdf(run_id=run_id, store=store)
    words = _words(pdf)

    assert "?" not in "".join(words), "replacement characters in a Farsi report"
    assert _plain("آزمایش دسته‌بندی") <= words, "the run name"
    assert _plain(t("pdf.epochs", "fa")) <= words, "the chrome"
    assert _plain(phase_name("learning", "fa")) <= words, "the phase name"
    assert {w.strip(".") for w in words} >= _plain(NARRATIVE), "the narrative"
    assert "This report is in English" not in " ".join(words)


def test_the_font_is_embedded_and_licensed() -> None:
    fonts = Path(__file__).resolve().parents[2] / "src" / "epochix" / "exporters" / "fonts"
    assert (fonts / "Vazirmatn-Regular.ttf").stat().st_size > 50_000
    assert (fonts / "Vazirmatn-Bold.ttf").stat().st_size > 50_000
    assert "SIL Open Font License" in (fonts / "OFL.txt").read_text(encoding="utf-8")


def test_an_english_report_does_not_embed_a_font(tmp_path: Path) -> None:
    """Latin-script reports keep the core fonts: smaller, identical everywhere."""
    run_id, store = _store(tmp_path)
    run = store.get_run(run_id)
    assert run is not None
    from epochix.exporters._pdf_render import render_pdf

    pdf = render_pdf(run, store.get_story_frames(run_id), store.get_metric_events(run_id), "en")
    assert b"FontFile2" not in pdf
