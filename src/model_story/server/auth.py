from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from model_story.config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

_SettingsDep = Annotated[Settings, Depends(get_settings)]
_BearerDep = Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)]


async def require_auth(
    settings: _SettingsDep,
    credentials: _BearerDep,
) -> None:
    """FastAPI dependency: enforce bearer-token auth when configured.

    If ``MODEL_STORY_AUTH_TOKEN`` is empty (the default), all requests are
    allowed (local-first, zero-config principle).  Set the env var to
    require a token in the ``Authorization: Bearer <token>`` header.
    """
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
