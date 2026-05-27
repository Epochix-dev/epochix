"""PDF export — CSS slide deck via WeasyPrint.

One page per major milestone + final summary page.
WeasyPrint is an optional dependency (``pip install epochix[pdf]``).

Page layout:
  - Cover page: run name, grade, task, finished date
  - Phase summary pages: one per phase reached
  - Final grade page: grade + final narrative
  - Engineer appendix: key metrics table
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from epochix.models import MetricEvent, Run, StoryFrame
    from epochix.store.sqlite_store import RunStore

_GRADE_COLOR: dict[str, str] = {
    "A+": "#52e88a", "A": "#3cd06a", "A-": "#7ee84a",
    "B+": "#60a5fa", "B": "#4a8cf7", "B-": "#7bb4f8",
    "C+": "#fb923c", "C": "#fbbf24", "C-": "#fcd34d",
    "D":  "#f97316", "F": "#ef4444", "I":  "#6b7280",
}

_PHASE_EMOJI: dict[str, str] = {
    "awakening":     "🌱",
    "learning":      "📚",
    "understanding": "💡",
    "mastering":     "⚡",
    "polishing":     "✨",
}


def build_pdf(run_id: str, store: RunStore) -> bytes:
    """Build a PDF slide deck for a finished run.

    Returns
    -------
    bytes
        Raw PDF bytes.

    Raises
    ------
    ImportError
        If WeasyPrint is not installed
        (``pip install "epochix[pdf]"``).
    ValueError
        If the run is not found in the store.
    """
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "WeasyPrint is required for PDF export. "
            'Install it with: pip install "epochix[pdf]"'
        ) from exc

    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)

    html_str = _build_html(run, frames, events)
    return HTML(string=html_str).write_pdf()  # type: ignore[no-any-return]


# ── HTML builder ─────────────────────────────────────────────────────────────

def _build_html(
    run: Run,
    frames: Sequence[StoryFrame],
    events: Sequence[MetricEvent],
) -> str:
    run_name  = run.name or run.id
    grade_str = run.final_grade.value if run.final_grade else "—"
    grade_col = _GRADE_COLOR.get(grade_str, "#888")
    task_str  = run.task_type.value if run.task_type else "custom"
    summary   = run.story_summary or ""
    fin_str   = run.finished_at.strftime("%Y-%m-%d") if run.finished_at else ""

    slides: list[str] = []

    # Cover slide
    slides.append(f"""
      <div class="slide slide-cover">
        <div class="cover-grade" style="color:{grade_col}">{_esc(grade_str)}</div>
        <h1 class="cover-title">{_esc(run_name)}</h1>
        <p class="cover-task">{_esc(task_str)}</p>
        {f'<p class="cover-date">{_esc(fin_str)}</p>' if fin_str else ""}
        {f'<p class="cover-summary">{_esc(summary)}</p>' if summary else ""}
      </div>
    """)

    # Phase slides (one per unique phase)
    seen_phases: set[str] = set()
    for frame in frames:
        phase_str = frame.phase.value if frame.phase else ""
        if not phase_str or phase_str in seen_phases:
            continue
        seen_phases.add(phase_str)
        phase_emoji = _PHASE_EMOJI.get(phase_str, "")
        narrative = frame.narrative or ""
        epoch_str = f"Epoch {frame.epoch}" if frame.epoch is not None else ""
        pv = frame.primary_metric_value
        primary_str = f"{pv:.4f}" if pv is not None else ""

        slides.append(f"""
          <div class="slide slide-phase">
            <div class="phase-header">
              <span class="phase-emoji">{phase_emoji}</span>
              <span class="phase-name">{_esc(phase_str.title())}</span>
              {f'<span class="phase-epoch">{_esc(epoch_str)}</span>' if epoch_str else ""}
            </div>
            {f'<p class="phase-narrative">{_esc(narrative)}</p>' if narrative else ""}
            {(
                f'<div class="phase-value">Primary metric: '
                f'<strong>{_esc(primary_str)}</strong></div>'
            ) if primary_str else ""}
          </div>
        """)

    # Milestone slides
    milestone_items: list[tuple[str, str]] = []
    for frame in frames:
        for m in frame.milestones:
            msg = m.message or m.kind.replace("_", " ").title()
            ep  = f" — Epoch {frame.epoch}" if frame.epoch is not None else ""
            milestone_items.append((m.kind, f"{msg}{ep}"))

    if milestone_items:
        items_html = "\n".join(
            f'<li class="ms-item">{_esc(msg)}</li>'
            for _, msg in milestone_items
        )
        slides.append(f"""
          <div class="slide slide-milestones">
            <h2>Key Milestones</h2>
            <ul class="ms-list">{items_html}</ul>
          </div>
        """)

    # Metrics appendix
    if events:
        latest: dict[str, float] = {}
        for ev in events:
            latest[ev.canonical_key] = ev.value
        rows = "\n".join(
            f"<tr><td><code>{_esc(k)}</code></td><td>{v:.4f}</td></tr>"
            for k, v in sorted(latest.items())
        )
        slides.append(f"""
          <div class="slide slide-appendix">
            <h2>Engineer Appendix — Final Metrics</h2>
            <table class="metrics-table">
              <thead><tr><th>Metric</th><th>Value</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        """)

    slides_html = "\n".join(slides)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<style>
{_PDF_CSS}
</style>
</head>
<body>
{slides_html}
</body>
</html>
"""


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_PDF_CSS = """
@page {
  size: A4 landscape;
  margin: 0;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Helvetica Neue', Arial, sans-serif;
  background: #fff;
}

.slide {
  width: 297mm;
  height: 210mm;
  padding: 32mm 36mm;
  page-break-after: always;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: #0d0d0f;
  color: #f0f0f2;
}

/* Cover */
.slide-cover {
  align-items: center;
  text-align: center;
  background: linear-gradient(135deg, #0d0d0f 0%, #1a1030 100%);
}
.cover-grade {
  font-size: 96pt;
  font-weight: 300;
  line-height: 1;
  margin-bottom: 12pt;
}
.cover-title {
  font-size: 32pt;
  font-weight: 300;
  margin-bottom: 8pt;
}
.cover-task {
  font-size: 14pt;
  color: #a0a0aa;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 16pt;
}
.cover-date, .cover-summary {
  font-size: 12pt;
  color: #808088;
  max-width: 240mm;
}

/* Phase slides */
.slide-phase {
  background: #0d0d0f;
}
.phase-header {
  display: flex;
  align-items: baseline;
  gap: 12pt;
  margin-bottom: 20pt;
}
.phase-emoji { font-size: 40pt; }
.phase-name  { font-size: 28pt; font-weight: 300; }
.phase-epoch { font-size: 12pt; color: #606068; }
.phase-narrative {
  font-size: 16pt;
  line-height: 1.6;
  color: #c0c0ca;
  font-style: italic;
  max-width: 220mm;
}
.phase-value {
  margin-top: 16pt;
  font-size: 13pt;
  color: #a0a0aa;
}

/* Milestones */
.slide-milestones h2,
.slide-appendix h2 {
  font-size: 22pt;
  font-weight: 300;
  margin-bottom: 20pt;
  color: #f0f0f2;
}
.ms-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10pt;
}
.ms-item {
  font-size: 13pt;
  color: #c0c0ca;
  padding-left: 20pt;
  position: relative;
}
.ms-item::before {
  content: "›";
  position: absolute;
  left: 0;
  color: #7c6dff;
}

/* Metrics table */
.metrics-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 12pt;
}
.metrics-table th {
  text-align: left;
  padding: 6pt 12pt;
  border-bottom: 1pt solid #333;
  color: #a0a0aa;
  font-weight: 500;
}
.metrics-table td {
  padding: 5pt 12pt;
  border-bottom: 1pt solid #222;
  color: #d0d0da;
}
.metrics-table code {
  font-family: 'Courier New', monospace;
  font-size: 11pt;
  color: #9090f0;
}
"""
