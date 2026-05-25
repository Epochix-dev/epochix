"""HTML export — self-contained single-file report.

The HTML file inlines:
- The compiled Vite JS bundle (inline ``<script type="module">``)
- The compiled CSS (inline ``<style>``)
- Run data as ``<script type="application/json" id="run-data">``

Target size: < 2 MB.  No network requests are required at view time.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model_story.store.sqlite_store import RunStore

# Path to the vendored Vite build output
_DIST = Path(__file__).parents[1] / "_frontend" / "dist"


def build_html(run_id: str, store: RunStore) -> str:
    """Build a self-contained HTML report for a finished run.

    Returns
    -------
    str
        Complete HTML document, safe to write to a ``.html`` file.

    Raises
    ------
    FileNotFoundError
        If the frontend bundle has not been built yet
        (run ``make build-frontend`` first).
    ValueError
        If the run is not found in the store.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    _require_bundle()

    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)

    run_data_json = json.dumps(
        {
            "run":    run.model_dump(mode="json"),
            "frames": [f.model_dump(mode="json") for f in frames],
            "events": [e.model_dump(mode="json") for e in events],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

    run_name  = _esc(run.name or run_id)
    grade_str = run.final_grade.value if run.final_grade else ""
    grade_esc = _esc(grade_str)
    sep       = " · " if grade_str else ""
    doc_title = f"{run_name}{sep}{grade_esc} — Model Learning Story"

    js_blob  = _read_asset("js")
    css_blob = _read_asset("css")

    return _build(
        doc_title=doc_title,
        run_name=run_name,
        grade=grade_esc,
        run_data_json=run_data_json,
        js_blob=js_blob,
        css_blob=css_blob,
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_bundle() -> None:
    if not (_DIST / "index.html").is_file():
        raise FileNotFoundError(
            f"Frontend bundle not found at {_DIST}. "
            "Run `make build-frontend` to build it first."
        )


def _read_asset(kind: str) -> str:
    """Read and concatenate all .js or .css asset files from dist/assets/."""
    assets_dir = _DIST / "assets"
    if not assets_dir.is_dir():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(assets_dir.glob(f"*.{kind}"))
    )


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def _build(  # noqa: PLR0913
    *,
    doc_title: str,
    run_name: str,
    grade: str,
    run_data_json: str,
    js_blob: str,
    css_blob: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{doc_title}</title>
  <style>
{css_blob}
  </style>
  <!-- Inline run data – read by main.js on startup (export mode) -->
  <script type="application/json" id="run-data">{run_data_json}</script>
</head>
<body>
  <div id="app">
    <header id="app-header">
      <div class="header-left">
        <span class="app-logo">&#9672;</span>
        <span class="run-name" id="run-name">{run_name}</span>
      </div>
      <div class="header-center">
        <span class="phase-badge" id="phase-badge">&mdash;</span>
      </div>
      <div class="header-right">
        <span class="grade-pill" id="grade-pill">{grade or "&mdash;"}</span>
        <button class="theme-toggle" id="theme-toggle" title="Toggle theme">&#9680;</button>
      </div>
    </header>
    <main id="app-main">
      <section class="hero-row">
        <div id="hero-panel" class="panel panel-brain">
          <canvas id="brain-canvas"></canvas>
        </div>
        <div id="journey-panel" class="panel panel-story">
          <div class="grade-card-wrap" id="grade-card-wrap"></div>
          <div class="narrative-text" id="narrative-text">
            <p class="narrative-placeholder">Loading&hellip;</p>
          </div>
          <div class="metaphor-cards" id="metaphor-cards"></div>
        </div>
      </section>
      <section class="metrics-row">
        <div id="skills-panel" class="panel panel-skills">
          <h3 class="panel-title">Skills</h3>
          <canvas id="skill-radar"></canvas>
        </div>
        <div class="panel panel-meter">
          <h3 class="panel-title">Confidence</h3>
          <div id="learning-meter"></div>
        </div>
        <div class="panel panel-confidence">
          <h3 class="panel-title">Metrics</h3>
          <div id="confidence-bars"></div>
        </div>
      </section>
      <section class="timeline-row">
        <div id="timeline-panel" class="panel panel-timeline">
          <h3 class="panel-title">Training Journey</h3>
          <div id="timeline-story"></div>
          <div id="epoch-scrubber-wrap"></div>
        </div>
      </section>
      <section class="engineer-row">
        <details id="tech-panel" class="panel panel-tech">
          <summary class="panel-title">
            Engineer Panel <span class="toggle-hint">&#9656;</span>
          </summary>
          <div id="tech-panel-content">
            <div class="chart-wrap"><canvas id="loss-chart"></canvas></div>
            <div class="chart-wrap"><canvas id="accuracy-chart"></canvas></div>
          </div>
        </details>
      </section>
    </main>
    <div id="toasts" aria-live="polite"></div>
  </div>
  <script type="module">
{js_blob}
  </script>
</body>
</html>
"""
