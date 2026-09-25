"""PDF export — the run as a report, rendered by epochix/exporters/_pdf_render.

Pure Python (fpdf2, a core dependency): a cover with the grade, a charts page,
every epoch, one page per training phase, final metrics, skills and the model.
A Farsi report embeds the bundled Vazirmatn font and needs the `pdf` extra for
text shaping (``pip install "epochix[pdf]"``); without it the report falls back
to English chrome and says so.

This module used to also hold a WeasyPrint HTML/CSS builder that nothing had
called since the switch to fpdf2, under a docstring still describing it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from epochix.store.sqlite_store import RunStore


class PdfUnavailable(RuntimeError):
    """PDF export cannot run here — the reason is in the message."""


_PDF_HELP = (
    "PDF export needs fpdf2, which epochix installs by default — this "
    "environment is missing it. Repair with: pip install --upgrade epochix"
)


def build_pdf(run_id: str, store: RunStore) -> bytes:
    """The PDF report for a run, in the language it was narrated in.

    Raises
    ------
    PdfUnavailable
        If fpdf2 is missing from this environment.
    ValueError
        If the run is not found in the store.
    """
    try:
        from epochix.exporters._pdf_render import render_pdf
    except ImportError as exc:  # pragma: no cover - fpdf2 is a core dependency
        raise PdfUnavailable(_PDF_HELP) from exc

    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)

    # The language the run was narrated in, recorded at creation.
    locale = str(run.config.get("locale", "en")) if run.config else "en"
    return render_pdf(run, frames, events, locale)
