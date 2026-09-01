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

from itertools import pairwise
from typing import TYPE_CHECKING, Any

from epochix.story_engine.grade import metric_lower_better

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


# Series colours, in the order they are assigned. Training and validation of
# the same family sit next to each other so a reader can tell the pair apart at
# a glance without reading the legend.
_SERIES_RGB: tuple[tuple[int, int, int], ...] = (
    (86, 156, 214),  # blue   - first series (usually train)
    (214, 108, 46),  # orange - second series (usually validation)
    (34, 160, 96),  # green
    (146, 108, 214),  # purple
)

_GRID = (232, 236, 245)

# Which canonical keys belong on which chart. A loss and an accuracy share no
# scale, so drawing them on one axis would make the smaller one a flat line
# along the bottom and imply it never moved.
_LOSS_KEYS = ("train_loss", "val_loss", "log_loss", "val_log_loss", "MSE", "val_MSE")
_QUALITY_KEYS = (
    "accuracy",
    "val_accuracy",
    "f1",
    "val_f1",
    "AUC",
    "val_AUC",
    "mAP",
    "mAP50",
    "IoU",
    "mIoU",
    "Dice",
    "R2",
    "val_R2",
)
_ERROR_KEYS = ("MAE", "val_MAE", "RMSE", "val_RMSE", "MAPE", "val_MAPE")


def _series(
    events: Sequence[MetricEvent], keys: Sequence[str]
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Collect (label, [(x, y)]) for the requested keys, in the given order.

    The x axis is the epoch when the run has one and the event index when it
    does not — a boosting round or a bare `iter` counter is still a real
    ordering, whereas inventing epoch numbers would not be.
    """
    grouped: dict[str, list[tuple[float, float]]] = {}
    for i, event in enumerate(events):
        if event.value is None or event.canonical_key not in keys:
            continue
        x = event.epoch if event.epoch is not None else float(i)
        grouped.setdefault(event.canonical_key, []).append((x, float(event.value)))
    out: list[tuple[str, list[tuple[float, float]]]] = []
    for key in keys:
        points = grouped.get(key)
        if points:
            out.append((key, sorted(points)))
    return out


def _line_chart(
    doc: Any,  # noqa: ANN401
    x: float,
    y: float,
    w: float,
    h: float,
    series: list[tuple[str, list[tuple[float, float]]]],
    title: str,
) -> None:
    """Draw one line chart. Nothing is drawn for an empty or flat-x series.

    The whole point of this product is the shape of a curve, and the PDF had
    none: a 20-epoch run exported five pages of four text lines each and not a
    single graphic. Every number needed was already loaded.
    """
    if not series:
        return

    xs = [px for _, pts in series for px, _ in pts]
    ys = [py for _, pts in series for _, py in pts]
    if not xs or not ys:
        return
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    if y_hi - y_lo < 1e-12:
        # A perfectly flat series still deserves to be shown, but a zero-height
        # span would divide by zero and put the line at an arbitrary height.
        y_lo, y_hi = y_lo - 1.0, y_hi + 1.0
    x_span = (x_hi - x_lo) or 1.0
    y_span = y_hi - y_lo

    _text(doc, 11, _INK, "B")
    doc.set_xy(x, y)
    doc.cell(w, 6, _ascii(title))

    top = y + 8.0
    plot_h = h - 8.0

    def px(vx: float) -> float:
        return x + (vx - x_lo) / x_span * w

    def py(vy: float) -> float:
        return top + plot_h - (vy - y_lo) / y_span * plot_h

    # Gridlines with their real values, so the axis is readable rather than
    # decorative.
    doc.set_line_width(0.15)
    _text(doc, 7, _MUTED)
    for i in range(4):
        gy = top + plot_h * i / 3.0
        doc.set_draw_color(*_GRID)
        doc.line(x, gy, x + w, gy)
        doc.set_xy(x + w + 1.0, gy - 2.0)
        doc.cell(16, 4, _ascii(f"{y_hi - y_span * i / 3.0:.4g}"))

    for index, (label, points) in enumerate(series):
        colour = _SERIES_RGB[index % len(_SERIES_RGB)]
        doc.set_draw_color(*colour)
        doc.set_line_width(0.6)
        if len(points) == 1:
            # One reading is a point, not a line. Drawing a segment would
            # invent a trend the run never had.
            only_x, only_y = points[0]
            doc.set_fill_color(*colour)
            doc.circle(px(only_x) - 0.8, py(only_y) - 0.8, 1.6, style="F")
        else:
            for (ax, ay), (bx, by) in pairwise(points):
                doc.line(px(ax), py(ay), px(bx), py(by))

        # Legend swatch, on the line's own colour.
        lx = x + index * 42.0
        ly = top + plot_h + 4.0
        doc.set_line_width(1.2)
        doc.line(lx, ly + 1.5, lx + 5.0, ly + 1.5)
        _text(doc, 8, _MUTED)
        doc.set_xy(lx + 6.5, ly - 0.5)
        doc.cell(34, 4, _ascii(label))

    # x axis extent, so "epoch 1 to 20" is stated rather than assumed.
    _text(doc, 7, _MUTED)
    doc.set_xy(x, top + plot_h + 0.5)
    doc.cell(20, 4, _ascii(f"{x_lo:g}"))
    doc.set_xy(x + w - 20.0, top + plot_h + 0.5)
    doc.cell(20, 4, _ascii(f"{x_hi:g}"), align="R")
    doc.set_line_width(0.2)


def _charts_page(doc: Any, events: Sequence[MetricEvent]) -> None:  # noqa: ANN401
    """A page of curves — the thing a training report exists to show."""
    panels = [
        ("Loss", _series(events, _LOSS_KEYS)),
        ("Quality", _series(events, _QUALITY_KEYS)),
        ("Error", _series(events, _ERROR_KEYS)),
    ]
    panels = [(t, s) for t, s in panels if s]
    if not panels:
        return

    doc.add_page()
    _text(doc, 22, _INK, "B")
    doc.cell(0, 12, "How the run moved", new_x="LMARGIN", new_y="NEXT")

    # Two panels per row, and the row height grows when there is only one row.
    # Fixed-height panels left two thirds of a landscape page blank, which is
    # the emptiness this whole change is about.
    # A single panel spans the width rather than sitting in a half-empty page;
    # a boosting run logs only a loss and was leaving the right half blank.
    per_row = 1 if len(panels) == 1 else 2
    chart_w = (_W - _MARGIN * 2 - 26.0) / per_row
    chart_h = 128.0 if len(panels) <= 2 else 62.0
    for i, (title, series) in enumerate(panels):
        col, row = i % per_row, i // per_row
        _line_chart(
            doc,
            _MARGIN + col * (chart_w + 20.0),
            32.0 + row * (chart_h + 18.0),
            chart_w,
            chart_h,
            series,
            title,
        )


def _fmt(value: float) -> str:
    """Four significant figures, without trailing noise on round numbers."""
    return f"{value:.4g}"


def _best_and_final(
    frames: Sequence[StoryFrame], lower_better: bool
) -> tuple[StoryFrame | None, StoryFrame | None]:
    """The run's best frame and its last, by the primary metric."""
    scored = [f for f in frames if f.primary_metric_value is not None]
    if not scored:
        return None, None
    best = (min if lower_better else max)(scored, key=lambda f: f.primary_metric_value)
    return best, scored[-1]


def _cover_facts(
    doc: Any,  # noqa: ANN401
    run: Run,
    frames: Sequence[StoryFrame],
    events: Sequence[MetricEvent],
) -> None:
    """The evidence behind the grade, on the page that states it.

    The cover used to carry a letter, an id, a task, a date and one sentence —
    nothing that showed why the letter was that letter. A grade is the loudest
    claim this product makes and it was the least supported thing on the page.
    """
    metric = run.primary_metric or ""
    lower_better = metric_lower_better(metric) or False
    best, final = _best_and_final(frames, lower_better)

    epochs = sorted({e.epoch for e in events if e.epoch is not None})
    rows: list[tuple[str, str]] = []

    if final is not None:
        rows.append((f"final {metric}", _fmt(final.primary_metric_value)))
    if best is not None and final is not None:
        at = f" (epoch {best.epoch:g})" if best.epoch is not None else ""
        rows.append((f"best {metric}", _fmt(best.primary_metric_value) + at))
        # The gap between best and final is the "should I have stopped
        # earlier?" answer, and it was nowhere in the document.
        if best.epoch is not None and final.epoch is not None and best.epoch != final.epoch:
            drift = final.primary_metric_value - best.primary_metric_value
            # Say which way. The sign alone is ambiguous: +0.002 on a log-loss
            # is the model getting WORSE, and a reader should not have to know
            # the metric's direction to read its own report.
            worse = (drift > 0) if lower_better else (drift < 0)
            rows.append(("since best", f"{_fmt(abs(drift))} {'worse' if worse else 'better'}"))
    if epochs:
        rows.append(("epochs", f"{epochs[0]:g} to {epochs[-1]:g} ({len(epochs)})"))
    if run.parser_used:
        rows.append(("read by", run.parser_used))

    if not rows:
        return

    doc.ln(4)
    width = 92.0
    left = (_W - width) / 2.0
    for label, value in rows:
        doc.set_x(left)
        _text(doc, 10, _MUTED)
        doc.cell(38, 6, _ascii(label))
        _text(doc, 10, _INK, "B")
        doc.cell(54, 6, _ascii(value), new_x="LMARGIN", new_y="NEXT")


def _epoch_table(doc: Any, frames: Sequence[StoryFrame], run: Run) -> None:  # noqa: ANN401
    """Every epoch, not only the three that changed phase.

    One page per phase rendered 3 pages for an 11-frame run: eight readings
    were simply absent from the report, including whichever one was the best.
    """
    rows = [f for f in frames if f.primary_metric_value is not None]
    if len(rows) < 2:
        return

    metric = run.primary_metric or ""
    lower_better = metric_lower_better(metric) or False
    best, _ = _best_and_final(rows, lower_better)

    columns = (
        ("epoch", 22.0),
        (metric or "value", 34.0),
        ("change", 26.0),
        ("phase", 34.0),
    )

    def start_page(*, first: bool) -> None:
        """Title and column headers. Repeated on every continuation page.

        A 40-round run overflows one page, and the second page used to open on
        a bare data row: five unlabelled columns of numbers with no title and
        no header anywhere on the sheet.
        """
        doc.add_page()
        _text(doc, 22, _INK, "B")
        doc.cell(
            0,
            12,
            "Every epoch" if first else "Every epoch (continued)",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        doc.ln(2)
        _text(doc, 9, _MUTED)
        for header, width in columns:
            doc.cell(width, 6, _ascii(header))
        doc.cell(0, 6, "grade", new_x="LMARGIN", new_y="NEXT")
        doc.set_draw_color(*_RULE)
        doc.line(_MARGIN, doc.get_y(), _W - _MARGIN, doc.get_y())
        doc.ln(1)

    start_page(first=True)

    row_h = 5.5
    previous: float | None = None
    for frame in rows:
        if doc.get_y() + row_h > _H - _MARGIN:
            start_page(first=False)
        value = frame.primary_metric_value
        delta = "" if previous is None else f"{value - previous:+.4g}"
        previous = value
        is_best = best is not None and frame is best

        _text(doc, 9, _INK, "B" if is_best else "")
        doc.cell(22.0, 5.5, _ascii(f"{frame.epoch:g}" if frame.epoch is not None else "-"))
        doc.cell(34.0, 5.5, _ascii(_fmt(value)))
        doc.cell(26.0, 5.5, _ascii(delta))
        doc.cell(34.0, 5.5, _ascii(frame.phase.value.title() if frame.phase else ""))
        label = frame.grade.value if frame.grade else ""
        doc.cell(
            0,
            5.5,
            _ascii(f"{label}   <- best" if is_best else label),
            new_x="LMARGIN",
            new_y="NEXT",
        )


def _display_title(run: Run) -> str:
    """A cover title that is readable, even when the name is not renderable.

    fpdf2's core fonts are Latin-1, so a Farsi or CJK name comes back from
    `_ascii` as a row of question marks: "??????" told a reader nothing and
    looked like corruption rather than a limitation. Whatever survives is kept
    ("آزمایش mixed 実験" keeps "mixed", "café" keeps itself); when nothing
    legible survives the run id is used, which is at least a real identifier.

    The untouched name still reaches the document metadata, which is UTF-16 and
    needs no font — so the viewer's title bar and the file properties show it
    correctly whatever the page can draw.
    """
    name = run.name or run.id
    rendered = _ascii(name).replace("?", " ").strip()
    rendered = " ".join(rendered.split())
    if sum(ch.isalnum() for ch in rendered) < 2:
        return run.id
    if len(rendered) > 56:
        # ASCII dots, not U+2026. This function exists to hand the core fonts
        # something they can encode, and an ellipsis is outside Latin-1 — it
        # raised FPDFUnicodeEncodingException on every over-long name.
        rendered = rendered[:53] + "..."
    return rendered


def render_pdf(
    run: Run,
    frames: Sequence[StoryFrame],
    events: Sequence[MetricEvent],
) -> bytes:
    """The run as a PDF: cover, one page per phase, milestones, metrics."""
    doc = _pdf()
    # PDF metadata is UTF-16 and needs no embedded font, so the true name
    # survives here even when the page can only draw Latin-1.
    doc.set_title(run.name or run.id)
    doc.set_subject(f"epochix training report - {run.task_type.value if run.task_type else 'run'}")

    grade = run.final_grade.value if run.final_grade else "—"
    grade_rgb = _GRADE_RGB.get(grade, (122, 132, 160))

    # ── Cover ────────────────────────────────────────────────────────────
    doc.add_page()
    doc.set_y(_H * 0.28)
    _text(doc, 72, grade_rgb, "B")
    doc.cell(0, 26, _ascii(grade), align="C", new_x="LMARGIN", new_y="NEXT")
    _text(doc, 26, _INK, "B")
    doc.cell(0, 14, _display_title(run), align="C", new_x="LMARGIN", new_y="NEXT")
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

    _cover_facts(doc, run, frames, events)

    _charts_page(doc, events)
    _epoch_table(doc, frames, run)

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
