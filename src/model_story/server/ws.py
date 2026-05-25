from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from model_story.models import WSMessage
from model_story.server.auth import token_ok
from model_story.server.hub import Hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

_HEARTBEAT_INTERVAL = 15.0  # seconds


@router.websocket("/ws/live/{run_id}")
async def ws_live(
    websocket: WebSocket,
    run_id: str,
    last_seq: int = -1,
    token: str | None = None,
) -> None:
    """WebSocket live feed: ``WS /ws/live/{run_id}?last_seq=N``.

    The client may pass ``last_seq`` to resume from a known sequence
    number; the server replays buffered frames with seq > last_seq before
    streaming live events.

    Message envelope (JSON):

    .. code-block:: json

        {
          "v": 1,
          "type": "story_frame" | "milestone" | "warning" | "complete" | "ping",
          "run_id": "01J...",
          "seq": 42,
          "ts": "2026-05-15T12:34:56Z",
          "payload": { ... }
        }

    Heartbeat pings are sent every 15 s; a ``complete`` message signals
    end-of-run.

    When ``MODEL_STORY_AUTH_TOKEN`` is set, clients must pass a matching
    ``?token=`` query parameter (browsers cannot set WS Authorization headers).
    """
    if not token_ok(websocket.app.state.settings, token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    hub: Hub = websocket.app.state.hub
    queue = await hub.subscribe(run_id, last_seq=last_seq)

    ping_msg = hub.make_message(
        msg_type="ping",
        run_id=run_id,
        seq=-1,
        payload={},
    )

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text(ping_msg.model_dump_json())
            except Exception:  # noqa: BLE001
                break

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            try:
                msg: WSMessage | None = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keep connection alive even if the run is quiet
                continue

            if msg is None:
                # End-of-stream sentinel
                complete = hub.make_message(
                    msg_type="complete",
                    run_id=run_id,
                    seq=-1,
                    payload={},
                )
                await websocket.send_text(complete.model_dump_json())
                break

            await websocket.send_text(msg.model_dump_json())

            if msg.type == "complete":
                break

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected: run_id=%s", run_id)
    except Exception:  # noqa: BLE001
        logger.exception("WebSocket error: run_id=%s", run_id)
    finally:
        heartbeat_task.cancel()
        hub.unsubscribe(run_id, queue)
