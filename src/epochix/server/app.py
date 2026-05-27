from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from epochix.config import Settings
from epochix.server.hub import Hub
from epochix.store.sqlite_store import RunStore

logger = logging.getLogger(__name__)

# Path to the vendored frontend bundle
_FRONTEND_DIR = Path(__file__).parents[1] / "_frontend" / "dist"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle for the FastAPI app."""
    settings: Settings = app.state.settings

    store = RunStore(db_path=settings.db)
    hub = Hub()
    # engine_map holds active StoryEngine instances keyed by run_id.
    # The pipeline uses this to route metric events to the correct engine.
    engine_map: dict[str, Any] = {}

    app.state.store = store
    app.state.hub = hub
    app.state.engine_map = engine_map

    logger.info("epochix server starting (db=%s)", settings.db)
    yield
    logger.info("epochix server shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory.

    Parameters
    ----------
    settings:
        Override the default settings (useful in tests).  When *None*,
        settings are read from environment variables / ``.env`` file.
    """
    if settings is None:
        from epochix.config import get_settings

        settings = get_settings()

    # API docs reveal every route (incl. delete / event push). Hide them by
    # default; expose only when an auth_token is configured (the operator has
    # opted in) or EPOCHIX_EXPOSE_DOCS is set explicitly.
    _docs_visible = settings.expose_docs or bool(settings.auth_token)

    app = FastAPI(
        title="epochix",
        description="Visual storytelling for deep learning training runs.",
        version="0.1.0",
        lifespan=_lifespan,
        docs_url="/api/docs" if _docs_visible else None,
        redoc_url="/api/redoc" if _docs_visible else None,
        openapi_url="/api/openapi.json" if _docs_visible else None,
    )

    # Store settings so lifespan can read them
    app.state.settings = settings

    # --- CORS -----------------------------------------------------------
    # Default is *no* CORS middleware → same-origin only (the browser's SOP
    # protects the local dashboard from drive-by exfiltration by pages on
    # other sites). Cross-origin access is opt-in via EPOCHIX_CORS_ORIGINS,
    # which accepts a comma-separated list (or the explicit "*" wildcard).
    # Credentialed CORS (cookies) is only enabled with explicit origins —
    # wildcard-origin + allow-credentials is rejected by browsers anyway and
    # is a known foot-gun.
    _origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if _origins:
        _wildcard = _origins == ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=_origins,
            allow_credentials=not _wildcard,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # --- API routers ----------------------------------------------------
    from epochix.server.routes_export import router as export_router
    from epochix.server.routes_runs import router as runs_router
    from epochix.server.routes_snapshot import router as snapshot_router
    from epochix.server.sse import router as sse_router
    from epochix.server.ws import router as ws_router

    app.include_router(runs_router)
    app.include_router(snapshot_router)
    app.include_router(export_router)
    app.include_router(ws_router)
    app.include_router(sse_router)

    # --- Static files (frontend) ----------------------------------------
    # Serve the Vite bundle if it has been built (index.html must exist).
    # Absent during development / CI — the server operates in API-only mode.
    _index_html = _FRONTEND_DIR / "index.html"
    if _index_html.is_file():
        from fastapi.responses import FileResponse

        # SPA catch-all: /v/<run_id>, /compare and root return index.html
        @app.get("/v/{path:path}", include_in_schema=False)
        async def _spa_view(path: str) -> FileResponse:  # noqa: ARG001
            return FileResponse(str(_index_html))

        @app.get("/compare", include_in_schema=False)
        async def _spa_compare() -> FileResponse:
            return FileResponse(str(_index_html))

        @app.get("/", include_in_schema=False)
        async def _spa_root() -> FileResponse:
            return FileResponse(str(_index_html))

        # Serve hashed assets (JS/CSS chunks from Vite)
        _assets_dir = _FRONTEND_DIR / "assets"
        if _assets_dir.is_dir():
            app.mount(
                "/assets",
                StaticFiles(directory=str(_assets_dir)),
                name="assets",
            )
    else:
        logger.debug("Frontend not built at %s — API-only mode", _FRONTEND_DIR)

    return app
