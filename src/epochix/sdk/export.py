"""Export API — ``from epochix import export``."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from epochix.models import Run

ExportFormat = Literal["html", "pdf", "md", "json"]


def export(
    run: Run,
    fmt: ExportFormat = "html",
    *,
    output: str | Path | None = None,
    db: str | None = None,
) -> Path:
    """Export a run to a file.

    Parameters
    ----------
    run:
        A completed :class:`~epochix.models.Run`.
    fmt:
        Export format: ``"html"``, ``"pdf"``, ``"md"``, or ``"json"``.
    output:
        Output path.  Defaults to ``<run_id>.<fmt>`` in the current directory.
    db:
        SQLite DB containing the run (defaults to the configured DB).

    Returns
    -------
    Path
        Absolute path to the written file.
    """
    import json

    from epochix.config import get_settings
    from epochix.store.sqlite_store import RunStore

    settings = get_settings()
    store = RunStore(db_path=db or settings.db)

    out = Path(output) if output else Path(f"{run.id}.{fmt}")

    if fmt == "json":
        frames = store.get_story_frames(run.id)
        events = store.get_metric_events(run.id)
        payload = {
            "run": run.model_dump(mode="json"),
            "frames": [f.model_dump(mode="json") for f in frames],
            "events": [e.model_dump(mode="json") for e in events],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    elif fmt == "md":
        from epochix.exporters.markdown_export import build_markdown

        md = build_markdown(run_id=run.id, store=store)
        out.write_text(md, encoding="utf-8")

    elif fmt == "html":
        from epochix.exporters.html_export import build_html

        html = build_html(run_id=run.id, store=store)
        out.write_text(html, encoding="utf-8")

    elif fmt == "pdf":
        from epochix.exporters.pdf_export import build_pdf

        pdf_bytes = build_pdf(run_id=run.id, store=store)
        out.write_bytes(pdf_bytes)

    return out.resolve()
