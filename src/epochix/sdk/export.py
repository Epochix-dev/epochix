"""Export API — ``from epochix import export``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from epochix.models import Run

ExportFormat = Literal["html", "pdf", "md", "json"]
_FORMATS: tuple[str, ...] = ("html", "pdf", "md", "json")


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
        SQLite DB containing the run.  Not needed for a run returned by
        :func:`~epochix.sdk.parse.parse`, which is read from where it was
        parsed into; for any other run it defaults to the configured DB.

    Returns
    -------
    Path
        Absolute path to the written file.

    Raises
    ------
    ValueError
        If *fmt* is not one of the four formats, or the run is not in the
        database it was looked for in.  Nothing is written in either case.
    """
    from epochix.sdk._stores import store_holding

    # An unknown format used to fall through every branch below and return
    # the path of a file that had not been written.
    if fmt not in _FORMATS:
        raise ValueError(f"Unknown export format {fmt!r}: choose one of {', '.join(_FORMATS)}.")

    store = store_holding(run, db)

    out = Path(output) if output else Path(f"{run.id}.{fmt}")

    if fmt == "json":
        from epochix.exporters.json_export import build_json

        out.write_text(build_json(run_id=run.id, store=store), encoding="utf-8")

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
