"""FastAPI server for epochix.

Entry point: :func:`create_app` returns a configured :class:`fastapi.FastAPI`
instance.  Run with::

    uvicorn epochix.server:app --reload

or via the CLI::

    epochix serve --port 7860
"""
from __future__ import annotations

from epochix.server.app import create_app

# Convenience ASGI app for uvicorn/gunicorn direct invocation
app = create_app()

__all__ = ["app", "create_app"]
