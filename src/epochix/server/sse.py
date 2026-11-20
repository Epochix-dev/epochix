from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from epochix.models import WSMessage
from epochix.server.auth import token_ok
from epochix.server.hub import Hub
from epochix.server.jsonsafe import ws_json
from epochix.server.logsafe import log_safe

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sse"])

_HEARTBEAT_INTERVAL = 15.0  # seconds
_CONTENT_TYPE = "text/event-stream; charset=utf-8"
# Messages that are part of the run's sequence, and so carry an event id.
_SEQUENCED = frozenset({"story_frame", "milestone", "warning"})


def _resume_after(last_seq: int, last_event_id: str | None) -> int:
    """Where a connection resumes: after ``last_seq``, or after the browser's
    ``Last-Event-ID`` when it reconnects by itself.

    EventSource reconnects to the URL it was opened with, so its ``last_seq``
    is where the first connection started; the id of the last event it got
    arrives in the header. Without it a reconnect replayed the run from there.
    """
    if last_event_id is None:
        return last_seq
    try:
        seen = int(last_event_id.strip())
    except ValueError:
        return last_seq
    return max(last_seq, seen)


def _event(msg: WSMessage) -> str:
    data = f"data: {ws_json(msg)}\n\n"
    if msg.type in _SEQUENCED and msg.seq >= 0:
        return f"id: {msg.seq}\n{data}"
    return data


@router.get("/sse/live/{run_id}")
async def sse_live(
    request: Request,
    run_id: str,
    last_seq: int = -1,
    token: str | None = None,
) -> StreamingResponse:
    """SSE live feed: ``GET /sse/live/{run_id}?last_seq=N``.

    Fallback for clients behind strict proxies that block WebSocket upgrades.
    Event format (each message is one SSE ``data:`` line):

    .. code-block:: text

        data: {"v":1,"type":"story_frame","run_id":"01J...","seq":42,...}

    Heartbeat comments (``:``) are sent every 15 s to keep the connection
    alive through intermediaries. Frames, milestones and warnings carry their
    seq as the event ``id``, so a browser that reconnects by itself resumes
    after the last one it received (``Last-Event-ID``).

    When ``EPOCHIX_AUTH_TOKEN`` is set, clients must pass a matching
    ``?token=`` query parameter (EventSource cannot set Authorization headers).
    """
    if not token_ok(request.app.state.settings, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token"
        )
    hub: Hub = request.app.state.hub
    resume = _resume_after(last_seq, request.headers.get("last-event-id"))
    queue = await hub.subscribe(run_id, last_seq=resume)
    loop = asyncio.get_running_loop()

    async def _event_stream() -> AsyncIterator[str]:
        deadline = loop.time() + _HEARTBEAT_INTERVAL
        try:
            while True:
                if await request.is_disconnected():
                    break

                timeout = max(0.0, deadline - loop.time())
                try:
                    msg: WSMessage | None = await asyncio.wait_for(queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    deadline = loop.time() + _HEARTBEAT_INTERVAL
                    continue

                deadline = loop.time() + _HEARTBEAT_INTERVAL

                if msg is None:
                    complete_payload = json.dumps(
                        {"v": 1, "type": "complete", "run_id": run_id, "seq": -1, "payload": {}}
                    )
                    yield f"data: {complete_payload}\n\n"
                    break

                yield _event(msg)

                if msg.type == "complete":
                    break

        except Exception:  # noqa: BLE001
            logger.exception("SSE stream error: run_id=%s", log_safe(run_id))
        finally:
            hub.unsubscribe(run_id, queue)

    return StreamingResponse(
        _event_stream(),
        media_type=_CONTENT_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
