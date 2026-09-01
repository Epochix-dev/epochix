"""PDF export, which now works from the base install.

WeasyPrint was replaced by fpdf2 so that `pip install epochix` is the only
install anyone needs. WeasyPrint could never be a default: on Windows
`pip install weasyprint` SUCCEEDS and the import then dies loading GTK, so
making it core would have broken the base install for a whole platform.
"""

from __future__ import annotations

import re
import zlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epochix.enums import Grade, Phase, TaskType
from epochix.exporters.pdf_export import build_pdf
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.store.sqlite_store import RunStore


def _store(tmp_path: Path, *, name: str) -> tuple[str, RunStore]:
    # Each call gets its own directory: the run id is fixed, so two stores
    # sharing a path collide on the primary key.
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = RunStore(str(tmp_path / "t.db"))
    run_id = "01PDFTESTRUN"
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
    for i in range(1, 6):
        store.append_metric_event(
            MetricEvent(
                run_id=run_id,
                seq=i,
                timestamp=datetime.now(tz=timezone.utc),
                epoch=float(i),
                canonical_key="val_accuracy",
                raw_key="val_accuracy",
                value=0.5 + i * 0.05,
            )
        )
        store.append_story_frame(
            StoryFrame(
                run_id=run_id,
                seq=i,
                epoch=float(i),
                phase=Phase.LEARNING if i > 1 else Phase.AWAKENING,
                grade=Grade.B,
                primary_metric="val_accuracy",
                primary_metric_value=0.5 + i * 0.05,
                narrative=f"Epoch {i}: accuracy climbs — steadily, not spectacularly.",
                progress=i / 5,
                confidence=0.8,
                task_type=TaskType.CLASSIFICATION,
            )
        )
    store.finish_run(run_id, final_grade=Grade.B, story_summary="A solid run.")
    return run_id, store


def _text_runs(pdf: bytes) -> list[str]:
    """Every drawn string. Content streams are deflate-compressed by fpdf2."""
    blob = ""
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            blob += zlib.decompress(m.group(1)).decode("latin-1")
        except zlib.error:
            continue
    return re.findall(r"\((.*?)\)\s*Tj", blob)


def test_pdf_export_needs_no_extra_install(tmp_path: Path) -> None:
    run_id, store = _store(tmp_path, name="plain run")
    pdf = build_pdf(run_id=run_id, store=store)

    assert pdf.startswith(b"%PDF-")
    assert b"%%EOF" in pdf[-2048:]
    assert len(pdf) > 1000


def test_the_pdf_carries_the_run(tmp_path: Path) -> None:
    """A PDF that opens but says nothing is the failure that matters here."""
    run_id, store = _store(tmp_path, name="plain run")
    runs = _text_runs(build_pdf(run_id=run_id, store=store))

    joined = " ".join(runs)
    assert "plain run" in joined, runs
    assert "B" in runs, "the grade is the headline of the cover"
    assert "classification" in joined
    assert "val_accuracy" in joined
    assert any("accuracy climbs" in r for r in runs), "narrative missing"


def test_text_is_real_text_not_a_picture(tmp_path: Path) -> None:
    """fpdf2 draws vector text, so the report stays selectable and searchable."""
    run_id, store = _store(tmp_path, name="plain run")
    assert _text_runs(build_pdf(run_id=run_id, store=store)), "no drawn strings at all"


def test_typography_is_transliterated_not_blanked(tmp_path: Path) -> None:
    """Core fonts are Latin-1 and the narratives are full of em dashes.

    A bare Latin-1 encode turned every one into "?" — "63.5% accuracy ? only
    one direction from here". The shared table maps them instead.
    """
    run_id, store = _store(tmp_path, name="plain run")
    runs = _text_runs(build_pdf(run_id=run_id, store=store))

    assert not [r for r in runs if "?" in r], (
        f"unmapped characters: {[r for r in runs if '?' in r]}"
    )
    assert any(" - " in r for r in runs), "em dash should have become a hyphen"


def test_a_name_outside_latin1_still_exports(tmp_path: Path) -> None:
    """A run name is a filename, so it can hold anything the filesystem allows.

    The justification used to be "epochix ships Farsi and French too", which
    the data did not match — the Japanese in it serves no shipped locale. The
    real reason is narrower and does not depend on locales at all: fpdf2's core
    fonts are Latin-1, and whatever cannot be encoded must degrade rather than
    raise. Farsi and CJK are here because they are the ranges that cannot.
    """
    run_id, store = _store(tmp_path, name="آزمایش mixed 実験")
    pdf = build_pdf(run_id=run_id, store=store)
    assert pdf.startswith(b"%PDF-")


def test_latin1_accents_survive_but_other_scripts_do_not(tmp_path: Path) -> None:
    """The line between "kept" and "lost", pinned so it cannot move silently.

    French accents round-trip through Latin-1; Farsi and CJK become "?". That
    is a real limitation of core fonts, disclosed in ROADMAP.md, and a reader
    of a Farsi-named run gets a title of question marks. If embedding a Unicode
    font ever changes this, it should change this test with it.
    """
    run_id, store = _store(tmp_path / "accents", name="café résumé")
    assert "café résumé" in " ".join(_text_runs(build_pdf(run_id=run_id, store=store)))

    run_id, store = _store(tmp_path / "farsi", name="آزمایش")
    rendered = " ".join(_text_runs(build_pdf(run_id=run_id, store=store)))
    assert "آزمایش" not in rendered
    # It used to render as "??????". The page now falls back to the run id
    # rather than printing replacement characters, and the real name travels
    # in the document metadata instead — see the metadata test below.
    assert "?" not in rendered
    assert run_id in rendered


def test_an_unknown_run_is_refused(tmp_path: Path) -> None:
    _, store = _store(tmp_path, name="plain run")
    with pytest.raises(ValueError, match="not found"):
        build_pdf(run_id="does-not-exist", store=store)


def _meta_title(pdf: bytes) -> str:
    import io

    import pypdfium2 as pdfium

    return pdfium.PdfDocument(io.BytesIO(pdf)).get_metadata_value("Title") or ""


def test_an_unrenderable_name_does_not_become_question_marks(tmp_path: Path) -> None:
    """A Farsi title used to render as "??????" — corruption, not a limitation.

    Whatever survives Latin-1 is kept; when nothing legible does, the run id is
    used, because a real identifier beats a row of replacement characters.
    """
    run_id, store = _store(tmp_path / "mixed", name="آزمایش mixed 実験")
    assert "mixed" in " ".join(_text_runs(build_pdf(run_id=run_id, store=store)))

    run_id, store = _store(tmp_path / "farsi", name="آزمایش")
    rendered = " ".join(_text_runs(build_pdf(run_id=run_id, store=store)))
    assert "?" not in rendered
    assert run_id in rendered


def test_the_real_name_survives_in_the_metadata(tmp_path: Path) -> None:
    """PDF metadata is UTF-16 and needs no embedded font, so the true name
    reaches the viewer's title bar whatever the page can draw."""
    pytest.importorskip("pypdfium2")
    # Subdirectories are numbered, not named after the run: a Windows path
    # segment cannot end in a space and "plain ascii"[:6] does.
    for i, name in enumerate(("آزمایش 実験 café", "café résumé", "plain ascii")):
        run_id, store = _store(tmp_path / f"run{i}", name=name)
        assert _meta_title(build_pdf(run_id=run_id, store=store)) == name
