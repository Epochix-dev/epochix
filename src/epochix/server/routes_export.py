from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response

from epochix.exporters.html_export import build_html
from epochix.exporters.markdown_export import build_markdown
from epochix.exporters.pdf_export import build_pdf
from epochix.server.auth import require_auth
from epochix.store.sqlite_store import RunStore

router = APIRouter(prefix="/api/export", tags=["export"])


def _store(request: Request) -> RunStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[RunStore, Depends(_store)]

_NOT_IMPL = (
    "This export format needs the bundled dashboard. "
    "Install the published wheel (which vendors it) or build the frontend: "
    "npm --prefix frontend run build."
)


@router.get(
    "/{run_id}/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_auth)],
)
async def export_html(
    run_id: str,
    store: StoreDep,
) -> HTMLResponse:
    """Generate a standalone, offline-viewable HTML report for the run."""
    _require_run(run_id, store)
    try:
        html = build_html(run_id=run_id, store=store)
    except (NotImplementedError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPL) from exc
    return HTMLResponse(content=html)


@router.get("/{run_id}/pdf", dependencies=[Depends(require_auth)])
async def export_pdf(
    run_id: str,
    store: StoreDep,
) -> Response:
    """Generate a PDF report for the run (requires the `pdf` extra)."""
    _require_run(run_id, store)
    try:
        pdf_bytes = build_pdf(run_id=run_id, store=store)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPL) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_attachment(run_id, "pdf"),
    )


@router.get("/{run_id}/md", dependencies=[Depends(require_auth)])
async def export_markdown(
    run_id: str,
    store: StoreDep,
) -> Response:
    """Generate a Markdown summary for the run."""
    _require_run(run_id, store)
    try:
        md = build_markdown(run_id=run_id, store=store)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPL) from exc
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers=_attachment(run_id, "md"),
    )


@router.get("/{run_id}/json", dependencies=[Depends(require_auth)])
async def export_json(
    run_id: str,
    store: StoreDep,
) -> Response:
    """Export the canonical run JSON (re-importable)."""
    from epochix.exporters.json_export import build_json

    _require_run(run_id, store)
    return Response(
        content=build_json(run_id=run_id, store=store),
        media_type="application/json",
        headers=_attachment(run_id, "json"),
    )


def _require_run(run_id: str, store: RunStore) -> None:
    """Raise 404 if the run doesn't exist."""
    if store.get_run(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


# Anything outside this set is dropped rather than escaped: a run id has no
# legitimate reason to contain a quote, a newline or a path separator, and a
# filename is not a place to be permissive.
_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9_.\-]")


def _attachment(run_id: str, ext: str) -> dict[str, str]:
    """Build the Content-Disposition header for a downloaded export.

    The id reaching here has already been found in the database, and ids
    created through the API are charset-constrained (see ``RunCreateRequest``).
    But a run inserted by the CLI or the SDK carries whatever id it was given,
    and a quote or a CRLF in a header value ends the value — so the id is
    sanitised at the point of use rather than trusted to have been validated
    somewhere upstream.
    """
    safe = _UNSAFE_IN_FILENAME.sub("_", run_id)[:100] or "run"
    return {"Content-Disposition": f'attachment; filename="{safe}.{ext}"'}
