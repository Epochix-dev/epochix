from __future__ import annotations

import contextlib
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from epochix.models import MetricEvent, Run, StoryFrame
from epochix.server.auth import require_auth, require_destructive
from epochix.store.sqlite_store import RunStore

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
    """SDK push payload: a single metric event (pre-normalised).

    String fields are length-capped so a misconfigured client (or a hostile
    one on an open instance) can't bloat the DB with arbitrary blobs.
    """

    seq: int
    timestamp: datetime | None = None
    epoch: float | None = None
    step: int | None = None
    canonical_key: str = Field(max_length=128)
    raw_key: str = Field(max_length=256)
    value: float
    unit: str | None = Field(default=None, max_length=32)


class RunCreateRequest(BaseModel):
    """Create a new run and register a live StoryEngine for it."""

    # Charset-constrained because run ids are echoed into Content-Disposition
    # filenames by the export routes and used as pub/sub + DB keys. ULIDs and
    # UUIDs (the server-generated forms) always match.
    run_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    name: str | None = Field(default=None, max_length=256)
    task: str | None = Field(default=None, max_length=32)
    primary_metric: str | None = Field(default=None, max_length=64)
    total_epochs: int | None = Field(default=None, ge=0, le=10_000_000)
    locale: str = Field(default="en", max_length=8)
    #: Layers parsed by the caller, in the shape the Network State panel reads.
    #: A client that parsed the log itself (the VS Code extension does) has the
    #: model summary in hand; without this it had no way to hand it over, and
    #: the panel showed "No architecture to display" for a log that plainly
    #: contained one. Capped because it is untrusted input like any other.
    architecture: list[dict[str, Any]] | None = Field(default=None, max_length=512)


class DeleteResponse(BaseModel):
    deleted: bool
    run_id: str


class CompareRun(BaseModel):
    """One run's data for the multi-run comparison view."""

    run: Run
    frames: list[StoryFrame]
    metrics: list[MetricEvent]


class CompareResponse(BaseModel):
    runs: list[CompareRun]
    total: int
    #: Plain-English account of WHY the runs differ. Empty when they cannot be
    #: compared (different metrics) or have too little data.
    narrative: str = ""


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.post(
    "/runs",
    response_model=Run,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_destructive)],
)
async def create_run(
    body: RunCreateRequest,
    request: Request,
    store: StoreDep,
) -> Run:
    """Create a new run and register a live StoryEngine so that push_event can drive it."""
    from datetime import datetime, timezone

    from epochix.enums import TaskType
    from epochix.models import Run
    from epochix.story_engine import StoryEngine

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

    # Same handling as the SDK path in pipeline.py: park it in the run config
    # and broadcast, so a panel that is already open fills in rather than
    # waiting for a reload.
    if body.architecture:
        store.update_run_config(run_id, {**run.config, "architecture": body.architecture})
        hub = request.app.state.hub
        hub.publish(
            run_id,
            hub.make_message(
                msg_type="architecture",
                run_id=run_id,
                seq=-1,
                payload={"architecture": body.architecture},
            ),
        )

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
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> RunListResponse:
    """Return the most recent *limit* runs (newest first)."""
    runs = store.list_runs(limit=limit)
    return RunListResponse(runs=runs, total=len(runs))


@router.get("/compare", response_model=CompareResponse, dependencies=[Depends(require_auth)])
async def compare_runs(
    store: StoreDep,
    run_ids: str = "",
) -> CompareResponse:
    """Return frames + metric series for several runs in one call.

    ``GET /api/compare?run_ids=a,b,c`` — used by the multi-run comparison view.
    Unknown ids are skipped; at most 12 runs are returned.
    """
    ids = [r.strip() for r in run_ids.split(",") if r.strip()][:12]
    out: list[CompareRun] = []
    for rid in ids:
        run = store.get_run(rid)
        if run is None:
            continue
        out.append(
            CompareRun(
                run=run,
                frames=store.get_story_frames(rid),
                metrics=store.get_metric_events(rid),
            )
        )
    return CompareResponse(runs=out, total=len(out), narrative=_compare_narrative(out))


def _compare_narrative(runs: list[CompareRun]) -> str:
    """Explain the difference; a failure here must not break the comparison."""
    from epochix.story_engine.comparison import narrate_comparison, trajectory_from_frames

    trajectories = []
    for entry in runs:
        traj = trajectory_from_frames(
            entry.run.name or entry.run.id,
            list(entry.frames),
            grade=entry.run.final_grade.value if entry.run.final_grade else None,
        )
        if traj is not None:
            trajectories.append(traj)
    if len(trajectories) < 2:
        return ""
    return narrate_comparison(trajectories)


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
    dependencies=[Depends(require_destructive)],
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
    dependencies=[Depends(require_destructive)],
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
        from epochix.story_engine import StoryEngine

        engine: StoryEngine = engine_map[run_id]
        for frame in engine.process_all(event):
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
    from epochix import __version__

    return {"version": __version__, "api": "v1"}
