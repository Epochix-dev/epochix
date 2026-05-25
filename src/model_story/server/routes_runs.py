from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from model_story.models import MetricEvent, Run
from model_story.server.auth import require_auth
from model_story.store.sqlite_store import RunStore

router = APIRouter(prefix="/api", tags=["runs"])


# ------------------------------------------------------------------
# Dependency helpers
# ------------------------------------------------------------------


def _store(request: Request) -> RunStore:
    return request.app.state.store  # type: ignore[no-any-return]


StoreDep = Annotated[RunStore, Depends(_store)]


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class RunListResponse(BaseModel):
    runs: list[Run]
    total: int


class EventPushRequest(BaseModel):
    """SDK push payload: a single metric event (pre-normalised)."""

    seq: int
    timestamp: datetime | None = None
    epoch: float | None = None
    step: int | None = None
    canonical_key: str
    raw_key: str
    value: float
    unit: str | None = None


class RunCreateRequest(BaseModel):
    """Create a new run and register a live StoryEngine for it."""

    run_id: str | None = None
    name: str | None = None
    task: str | None = None
    primary_metric: str | None = None
    total_epochs: int | None = None
    locale: str = "en"


class DeleteResponse(BaseModel):
    deleted: bool
    run_id: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.post("/runs", response_model=Run, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_auth)])
async def create_run(
    body: RunCreateRequest,
    request: Request,
    store: StoreDep,
) -> Run:
    """Create a new run and register a live StoryEngine so that push_event can drive it."""
    from datetime import datetime, timezone

    from model_story.enums import TaskType
    from model_story.models import Run
    from model_story.story_engine import StoryEngine

    try:
        from ulid import ULID
        run_id = body.run_id or str(ULID())
    except Exception:
        import uuid
        run_id = body.run_id or str(uuid.uuid4())

    task: TaskType | None = None
    if body.task:
        with contextlib.suppress(ValueError):
            task = TaskType(body.task)

    run = Run(
        id=run_id,
        name=body.name,
        task_type=task or TaskType.CUSTOM,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric=body.primary_metric or "val_loss",
        parser_used="sdk",
    )
    store.create_run(run)

    engine = StoryEngine(
        run_id=run_id,
        task=task,
        primary_metric=body.primary_metric,
        total_epochs=body.total_epochs,
        locale=body.locale,
    )
    request.app.state.engine_map[run_id] = engine

    return run


@router.get("/runs", response_model=RunListResponse, dependencies=[Depends(require_auth)])
async def list_runs(
    store: StoreDep,
    limit: int = 100,
) -> RunListResponse:
    """Return the most recent *limit* runs (newest first)."""
    runs = store.list_runs(limit=limit)
    return RunListResponse(runs=runs, total=len(runs))


@router.get("/runs/{run_id}", response_model=Run, dependencies=[Depends(require_auth)])
async def get_run(
    run_id: str,
    store: StoreDep,
) -> Run:
    """Return run metadata."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.delete(
    "/runs/{run_id}",
    response_model=DeleteResponse,
    dependencies=[Depends(require_auth)],
)
async def delete_run(
    run_id: str,
    store: StoreDep,
) -> DeleteResponse:
    """Delete a run and all its associated data."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    store.delete_run(run_id)
    return DeleteResponse(deleted=True, run_id=run_id)


@router.post(
    "/runs/{run_id}/event",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_auth)],
)
async def push_event(
    run_id: str,
    body: EventPushRequest,
    request: Request,
    store: StoreDep,
) -> dict[str, Any]:
    """SDK push endpoint: accept a metric event and process it live.

    The server passes the event through the story engine and broadcasts the
    resulting frame to all connected WebSocket/SSE clients.
    """
    hub = request.app.state.hub
    engine_map: dict[str, Any] = request.app.state.engine_map

    event = MetricEvent(
        run_id=run_id,
        seq=body.seq,
        timestamp=body.timestamp or datetime.now(tz=timezone.utc),
        epoch=body.epoch,
        step=body.step,
        canonical_key=body.canonical_key,
        raw_key=body.raw_key,
        value=body.value,
        unit=body.unit,
    )

    store.append_metric_event(event)

    # Process through story engine if one is active for this run
    if run_id in engine_map:
        from model_story.story_engine import StoryEngine

        engine: StoryEngine = engine_map[run_id]
        frame = engine.process(event)
        if frame is not None:
            store.append_story_frame(frame)
            msg = hub.make_message(
                msg_type="story_frame",
                run_id=run_id,
                seq=frame.seq,
                payload=frame.model_dump(mode="json"),
            )
            hub.publish(run_id, msg)

    return {"accepted": True, "seq": body.seq}


# ------------------------------------------------------------------
# Health / version
# ------------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    from model_story import __version__

    return {"version": __version__, "api": "v1"}
