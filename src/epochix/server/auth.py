from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from epochix.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

# Hosts that count as the same machine. "testclient" is Starlette's TestClient
# transport (in-process, never network-reachable) — admitting it keeps tests
# working without weakening the policy for real requests.
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def token_ok(settings: Settings, token: str | None) -> bool:
    """Return True if *token* satisfies the configured auth policy.

    Used by the WebSocket/SSE endpoints, which cannot send an ``Authorization``
    header from the browser and therefore pass the token as a ``?token=`` query
    parameter. When no token is configured (the local-first default) access is
    always allowed.
    """
    if not settings.auth_token:
        return True
    return token is not None and secrets.compare_digest(token, settings.auth_token)


_BearerDep = Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)]


def _settings_for(request: Request) -> Settings:
    """Resolve settings from app.state (set in the lifespan handler) — the
    per-app configuration, NOT a fresh env-var read. Falls back to get_settings
    if the route is reached before lifespan startup (shouldn't happen in
    practice; defensive)."""
    state = request.app.state
    cfg = getattr(state, "settings", None)
    return cfg if isinstance(cfg, Settings) else get_settings()


async def require_auth(
    request: Request,
    credentials: _BearerDep,
) -> None:
    """FastAPI dependency: enforce bearer-token auth when configured.

    If ``EPOCHIX_AUTH_TOKEN`` is empty (the default), all requests are
    allowed (local-first, zero-config principle).  Set the env var to
    require a token in the ``Authorization: Bearer <token>`` header.
    """
    settings = _settings_for(request)
    if not settings.auth_token:
        return  # auth not configured — open access

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not secrets.compare_digest(credentials.credentials, settings.auth_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_destructive(
    request: Request,
    credentials: _BearerDep,
) -> None:
    """Stricter gate for write/delete endpoints.

    Local-first UX without an auth token is preserved by admitting *loopback*
    clients (same machine). Remote callers always need a Bearer token —
    otherwise a drive-by browser tab on another site (or a co-tenant on the
    LAN) could delete runs or inject metric events against an unauthenticated
    instance.
    """
    settings = _settings_for(request)
    if settings.auth_token:
        if credentials is None or not secrets.compare_digest(
            credentials.credentials, settings.auth_token
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return

    client_host = (request.client.host if request.client else "") or ""
    if client_host in _LOOPBACK_HOSTS:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Write endpoints require either an Authorization: Bearer token "
            "or a same-machine (loopback) client. Set EPOCHIX_AUTH_TOKEN "
            "to enable remote writes."
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )
