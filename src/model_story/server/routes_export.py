from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response

from model_story.exporters.html_export import build_html
from model_story.exporters.markdown_export import build_markdown
from model_story.exporters.pdf_export import build_pdf
from model_story.server.auth import require_auth
from model_story.store.sqlite_store import RunStore

router = APIRouter(prefix="/api/export", tags=["export"])


def _store(request: Request) -> RunStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[RunStore, Depends(_store)]

_NOT_IMPL = "Not yet available — build the frontend bundle first (Phase 11)"


@router.get(
    "/{run_id}/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_auth)],
)
async def export_html(
    run_id: str,
    store: StoreDep,
) -> HTMLResponse:
    """Generate a standalone HTML report for the run (Phase 11)."""
    _require_run(run_id, store)
    try:
        html = build_html(run_id=run_id, store=store)
    except (NotImplementedError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPL
        ) from exc
    return HTMLResponse(content=html)


@router.get("/{run_id}/pdf", dependencies=[Depends(require_auth)])
async def export_pdf(
    run_id: str,
    store: StoreDep,
) -> Response:
    """Generate a PDF slide deck for the run (Phase 11)."""
    _require_run(run_id, store)
    try:
        pdf_bytes = build_pdf(run_id=run_id, store=store)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPL
        ) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.pdf"'},
    )


@router.get("/{run_id}/md", dependencies=[Depends(require_auth)])
async def export_markdown(
    run_id: str,
    store: StoreDep,
) -> Response:
    """Generate a Markdown summary for the run (Phase 11)."""
    _require_run(run_id, store)
    try:
        md = build_markdown(run_id=run_id, store=store)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=_NOT_IMPL
        ) from exc
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.md"'},
    )


@router.get("/{run_id}/json", dependencies=[Depends(require_auth)])
async def export_json(
    run_id: str,
    store: StoreDep,
) -> Response:
    """Export the canonical run JSON (re-importable)."""
    import json

    _require_run(run_id, store)
    frames = store.get_story_frames(run_id)
    events = store.get_metric_events(run_id)
    run = store.get_run(run_id)
    assert run is not None  # guaranteed by _require_run

    payload = {
        "run": run.model_dump(mode="json"),
        "frames": [f.model_dump(mode="json") for f in frames],
        "events": [e.model_dump(mode="json") for e in events],
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
    )


def _require_run(run_id: str, store: RunStore) -> None:
    """Raise 404 if the run doesn't exist."""
    if store.get_run(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
