"""FastAPI server for model-story.

Entry point: :func:`create_app` returns a configured :class:`fastapi.FastAPI`
instance.  Run with::

    uvicorn model_story.server:app --reload

or via the CLI::

    model-story serve --port 7860
"""
from __future__ import annotations

from model_story.server.app import create_app

# Convenience ASGI app for uvicorn/gunicorn direct invocation
app = create_app()

__all__ = ["app", "create_app"]
