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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sse"])

_HEARTBEAT_INTERVAL = 15.0  # seconds
_CONTENT_TYPE = "text/event-stream; charset=utf-8"


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
    alive through intermediaries.

    When ``EPOCHIX_AUTH_TOKEN`` is set, clients must pass a matching
    ``?token=`` query parameter (EventSource cannot set Authorization headers).
    """
    if not token_ok(request.app.state.settings, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token"
        )
    hub: Hub = request.app.state.hub
    queue = await hub.subscribe(run_id, last_seq=last_seq)

    async def _event_stream() -> AsyncIterator[str]:
        deadline = asyncio.get_event_loop().time() + _HEARTBEAT_INTERVAL
        try:
            while True:
                if await request.is_disconnected():
                    break

                timeout = max(0.0, deadline - asyncio.get_event_loop().time())
                try:
                    msg: WSMessage | None = await asyncio.wait_for(
                        queue.get(), timeout=timeout
                    )
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    deadline = asyncio.get_event_loop().time() + _HEARTBEAT_INTERVAL
                    continue

                deadline = asyncio.get_event_loop().time() + _HEARTBEAT_INTERVAL

                if msg is None:
                    complete_payload = json.dumps(
                        {"v": 1, "type": "complete", "run_id": run_id, "seq": -1, "payload": {}}
                    )
                    yield f"data: {complete_payload}\n\n"
                    break

                yield f"data: {msg.model_dump_json()}\n\n"

                if msg.type == "complete":
                    break

        except Exception:  # noqa: BLE001
            logger.exception("SSE stream error: run_id=%s", run_id)
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
