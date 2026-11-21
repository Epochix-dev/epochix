from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from epochix.models import MetricEvent, Run, StoryFrame
from epochix.server.auth import require_auth
from epochix.store.sqlite_store import RunStore

router = APIRouter(prefix="/api", tags=["snapshot"])


def _store(request: Request) -> RunStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[RunStore, Depends(_store)]


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class SnapshotResponse(BaseModel):
    run_id: str
    run: Run | None = None  # full Run object including config (architecture etc.)
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
    """The log lines a run was read from, as stored: secrets redacted first.

    Lines are kept only when ``EPOCHIX_KEEP_RAW_LINES`` was on while the run
    was read. A run read without it answered 200 with no lines, which says the
    log was empty; it is told why there are none instead.
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    lines = store.get_raw_lines(run_id)
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No log lines were kept for this run. Set EPOCHIX_KEEP_RAW_LINES=true "
                "before a run is read to keep them."
            ),
        )
    return RawResponse(run_id=run_id, lines=lines, total_lines=len(lines))
