from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from model_story.models import MetricEvent, Run, StoryFrame
from model_story.server.auth import require_auth
from model_story.store.sqlite_store import RunStore

router = APIRouter(prefix="/api", tags=["snapshot"])


def _store(request: Request) -> RunStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[RunStore, Depends(_store)]


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class SnapshotResponse(BaseModel):
    run_id: str
    run: Run | None = None          # full Run object including config (architecture etc.)
    frames: list[StoryFrame]
    total_frames: int


class MetricsResponse(BaseModel):
    run_id: str
    events: list[MetricEvent]
    total_events: int


class RawResponse(BaseModel):
    run_id: str
    lines: list[str]
    total_lines: int


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.get(
    "/snapshot/{run_id}",
    response_model=SnapshotResponse,
    dependencies=[Depends(require_auth)],
)
async def get_snapshot(
    run_id: str,
    store: StoreDep,
) -> SnapshotResponse:
    """Return all story frames for a run (HTTP-cacheable initial load).

    The frontend fetches this on first paint, then opens a WebSocket/SSE
    connection with ``?last_seq=<last_frame.seq>`` to receive only deltas.
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    frames = store.get_story_frames(run_id)
    return SnapshotResponse(run_id=run_id, run=run, frames=frames, total_frames=len(frames))


@router.get(
    "/metrics/{run_id}",
    response_model=MetricsResponse,
    dependencies=[Depends(require_auth)],
)
async def get_metrics(
    run_id: str,
    store: StoreDep,
) -> MetricsResponse:
    """Return all metric events for a run (for the engineer panel)."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    events = store.get_metric_events(run_id)
    return MetricsResponse(run_id=run_id, events=events, total_events=len(events))


@router.get(
    "/raw/{run_id}",
    response_model=RawResponse,
    dependencies=[Depends(require_auth)],
)
async def get_raw_lines(
    run_id: str,
    store: StoreDep,
) -> RawResponse:
    """Return raw log lines for a run (only available when keep_raw_lines=True)."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    lines = store.get_raw_lines(run_id)
    return RawResponse(run_id=run_id, lines=lines, total_lines=len(lines))
