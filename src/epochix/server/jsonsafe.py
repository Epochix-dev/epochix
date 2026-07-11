"""JSON safety net for the server boundary.

Non-finite floats (NaN / ±Inf — e.g. a diverged training metric) are not valid
JSON. Python's ``json`` emits the literal ``NaN`` / ``Infinity`` tokens (which a
browser's ``JSON.parse`` rejects) and Starlette's ``JSONResponse`` raises a 500.
Either way a single diverged epoch would break the dashboard. These helpers null
out any non-finite value so every response and WebSocket frame is valid JSON,
regardless of which field it came from.
"""

from __future__ import annotations

import json
import math

from starlette.responses import JSONResponse

from epochix.models import WSMessage


def sanitize_nonfinite(obj: object) -> object:
    """Recursively replace non-finite floats with ``None`` (JSON ``null``)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_nonfinite(v) for v in obj]
    return obj


def ws_json(msg: WSMessage) -> str:
    """Serialise a WebSocket/SSE message to strictly valid JSON."""
    return json.dumps(sanitize_nonfinite(msg.model_dump(mode="json")), allow_nan=False)


class SafeJSONResponse(JSONResponse):
    """A ``JSONResponse`` that never 500s on a non-finite float."""

    def render(self, content: object) -> bytes:
        return json.dumps(
            sanitize_nonfinite(content),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
