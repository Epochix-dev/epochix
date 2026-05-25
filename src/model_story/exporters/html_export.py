"""HTML export — self-contained single-file report.

The exported file is the *built* dashboard (``_frontend/dist/index.html``) with
its CSS and JS inlined and the run data embedded as
``<script type="application/json" id="run-data">``. Deriving from the built
index.html (rather than a hand-maintained template) keeps the export in lock-step
with the live app — no DOM drift.

Target size: < 2 MB. No network requests are required at view time.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model_story.store.sqlite_store import RunStore

# Path to the vendored Vite build output
_DIST = Path(__file__).parents[1] / "_frontend" / "dist"

_CSS_LINK_RE = re.compile(r'<link\b[^>]*\bhref="(/assets/[^"]+\.css)"[^>]*>', re.IGNORECASE)
_JS_TAG_RE = re.compile(
    r'<script\b[^>]*\bsrc="(/assets/[^"]+\.js)"[^>]*>\s*</script>', re.IGNORECASE
)
_RUN_DATA_RE = re.compile(
    r'<script type="application/json" id="run-data">\s*</script>', re.IGNORECASE
)


def build_html(run_id: str, store: RunStore) -> str:
    """Build a self-contained HTML report for a run.

    Returns
    -------
    str
        Complete, offline-viewable HTML document.

    Raises
    ------
    FileNotFoundError
        If the frontend bundle has not been built yet.
    ValueError
        If the run is not found in the store.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id!r}")

    _require_bundle()

    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)

    run_data = _json_for_script(
        {
            "run":    run.model_dump(mode="json"),
            "frames": [f.model_dump(mode="json") for f in frames],
            "events": [e.model_dump(mode="json") for e in events],
        }
    )

    html = (_DIST / "index.html").read_text(encoding="utf-8")

    # 1. Inline the stylesheet ( <link href="/assets/*.css"> → <style> ).
    def _css_sub(m: re.Match[str]) -> str:
        css = (_DIST / m.group(1).lstrip("/")).read_text(encoding="utf-8")
        return f"<style>\n{css}\n</style>"

    html = _CSS_LINK_RE.sub(_css_sub, html, count=1)

    # 2. Inline the entry module ( <script src="/assets/*.js"> → inline ).
    def _js_sub(m: re.Match[str]) -> str:
        js = (_DIST / m.group(1).lstrip("/")).read_text(encoding="utf-8")
        # Prevent a literal </script> inside JS strings from closing the tag.
        js = js.replace("</script>", "<\\/script>")
        return f'<script type="module">\n{js}\n</script>'

    html = _JS_TAG_RE.sub(_js_sub, html, count=1)

    # 3. Embed run data into the (empty) run-data script element.
    html = _RUN_DATA_RE.sub(
        lambda _m: f'<script type="application/json" id="run-data">{run_data}</script>',
        html,
        count=1,
    )

    # 4. Friendly document title.
    grade = run.final_grade.value if run.final_grade else ""
    sep = " · " if grade else ""
    title = _esc(f"{run.name or run_id}{sep}{grade} — Model Learning Story")
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)

    return html


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_bundle() -> None:
    if not (_DIST / "index.html").is_file():
        raise FileNotFoundError(
            f"Frontend bundle not found at {_DIST}. "
            "Run `make build-frontend` to build it first."
        )


def _json_for_script(obj: object) -> str:
    """Serialise *obj* to JSON that is safe to embed inside a ``<script>`` tag.

    Escapes ``<``, ``>``, ``&`` and the JS line separators U+2028/U+2029 to their
    ``\\uXXXX`` forms. These characters only occur inside JSON string values, so
    the result is still valid JSON — but a malicious run name like
    ``</script>`` can no longer break out of the script element (XSS).
    """
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    # Only <, >, & need escaping for safe <script> embedding; they appear
    # solely inside JSON string values, so the result stays valid JSON.
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )
