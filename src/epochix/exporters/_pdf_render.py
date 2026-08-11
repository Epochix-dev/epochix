"""PDF rendering with no system libraries.

WeasyPrint produced a better-looking document and cannot be a default
dependency: on Windows ``pip install weasyprint`` succeeds and the import then
dies loading ``libgobject-2.0-0``, because it needs GTK. Shipping that in the
base install would break ``pip install epochix`` for a whole platform.

fpdf2 is pure Python (3.2 MB; fonttools, defusedxml, pillow — all wheels, no
system libraries), so PDF export works from the one install everyone already
does. The text stays real vector text, selectable and searchable, rather than
a rasterised page.

The layout mirrors the slides the HTML version produced: a cover carrying the
grade, one page per training phase, milestones, and a final-metrics appendix.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from epochix.models import MetricEvent, Run, StoryFrame

# Landscape A4 in mm — a report that is read on screen, not printed to be
# bound, so it matches a slide's proportions rather than a page's.
_W, _H = 297.0, 210.0
_MARGIN = 20.0

_INK = (26, 30, 46)
_MUTED = (122, 132, 160)
_RULE = (222, 226, 238)

_GRADE_RGB: dict[str, tuple[int, int, int]] = {
    "A+": (34, 160, 96),
    "A": (34, 160, 96),
    "A-": (52, 168, 110),
    "B+": (86, 156, 214),
    "B": (86, 156, 214),
    "B-": (104, 164, 216),
    "C+": (214, 158, 46),
    "C": (214, 158, 46),
    "C-": (216, 168, 70),
    "D": (214, 108, 46),
    "F": (198, 62, 62),
}


def _pdf() -> Any:  # noqa: ANN401 - fpdf2 ships no py.typed
    from fpdf import FPDF

    doc = FPDF(orientation="L", unit="mm", format="A4")
    doc.set_auto_page_break(auto=True, margin=_MARGIN)
    # Core fonts only: no font file to vendor, no licence to carry, and
    # identical output on every machine.
    doc.set_font("helvetica", size=12)
    return doc


def _text(doc: Any, size: int, colour: tuple[int, int, int], style: str = "") -> None:  # noqa: ANN401
    doc.set_font("helvetica", style=style, size=size)
    doc.set_text_color(*colour)


def _ascii(value: object) -> str:
    """Make text safe for fpdf2's Latin-1 core fonts.

    `transliterate` first, because it maps rather than blanks: the
    narratives are full of em dashes and curly quotes, and a bare Latin-1
    encode turned every one of them into "?" — "only one direction from here"
    read as "?  only one direction from here". Same table the CLI already uses
    for Windows consoles, so both surfaces degrade the same way.

    The replace() is the backstop for anything the table does not know. Losing
    one glyph beats losing the document, and run names come from log files, so
    genuinely arbitrary characters do arrive here.
    """
    from epochix.console import transliterate

    return transliterate(str(value)).encode("latin-1", "replace").decode("latin-1")


def render_pdf(
    run: Run,
    frames: Sequence[StoryFrame],
    events: Sequence[MetricEvent],
) -> bytes:
    """The run as a PDF: cover, one page per phase, milestones, metrics."""
    doc = _pdf()

    grade = run.final_grade.value if run.final_grade else "—"
    grade_rgb = _GRADE_RGB.get(grade, (122, 132, 160))

    # ── Cover ────────────────────────────────────────────────────────────
    doc.add_page()
    doc.set_y(_H * 0.28)
    _text(doc, 72, grade_rgb, "B")
    doc.cell(0, 26, _ascii(grade), align="C", new_x="LMARGIN", new_y="NEXT")
    _text(doc, 26, _INK, "B")
    doc.cell(0, 14, _ascii(run.name or run.id), align="C", new_x="LMARGIN", new_y="NEXT")
    _text(doc, 13, _MUTED)
    task = run.task_type.value if run.task_type else "custom"
    when = run.finished_at.strftime("%Y-%m-%d") if run.finished_at else ""
    doc.cell(
        0,
        8,
        _ascii(" · ".join(x for x in (task, when) if x)),
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    if run.story_summary:
        doc.ln(6)
        doc.set_x(_MARGIN * 2)
        _text(doc, 13, _INK)
        doc.multi_cell(_W - _MARGIN * 4, 7, _ascii(run.story_summary), align="C")

    # ── One page per phase, in the order the run moved through them ──────
    seen: set[str] = set()
    for frame in frames:
        phase = frame.phase.value if frame.phase else ""
        if not phase or phase in seen:
            continue
        seen.add(phase)

        doc.add_page()
        _text(doc, 11, _MUTED)
        epoch = f"Epoch {frame.epoch:g}" if frame.epoch is not None else ""
        doc.cell(0, 6, _ascii(epoch), new_x="LMARGIN", new_y="NEXT")
        _text(doc, 30, _INK, "B")
        doc.cell(0, 16, _ascii(phase.title()), new_x="LMARGIN", new_y="NEXT")

        value = frame.primary_metric_value
        if value is not None:
            _text(doc, 20, grade_rgb, "B")
            metric = frame.primary_metric or run.primary_metric or ""
            doc.cell(0, 12, _ascii(f"{metric}  {value:.4f}"), new_x="LMARGIN", new_y="NEXT")

        if frame.narrative:
            doc.ln(4)
            _text(doc, 14, _INK)
            doc.multi_cell(_W - _MARGIN * 2, 8, _ascii(frame.narrative))

    # ── Final metrics ────────────────────────────────────────────────────
    latest: dict[str, float] = {}
    for event in events:
        if event.value is not None:
            latest[event.canonical_key] = event.value
    if latest:
        doc.add_page()
        _text(doc, 22, _INK, "B")
        doc.cell(0, 14, "Final metrics", new_x="LMARGIN", new_y="NEXT")
        doc.ln(2)
        for key, value in sorted(latest.items()):
            _text(doc, 12, _MUTED)
            doc.cell(90, 8, _ascii(key))
            _text(doc, 12, _INK, "B")
            doc.cell(0, 8, f"{value:.4f}", new_x="LMARGIN", new_y="NEXT")
            doc.set_draw_color(*_RULE)
            doc.line(_MARGIN, doc.get_y(), _W - _MARGIN, doc.get_y())

    return bytes(doc.output())
