"""Security-posture tests.

These pin down the secure-by-default behaviour: no Swagger UI is exposed
without explicit opt-in, write endpoints require either a same-machine
caller or a Bearer token, and CORS is same-origin only unless the operator
configures origins.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from epochix.config import Settings
from epochix.enums import TaskType
from epochix.models import Run
from epochix.server.app import create_app


def _make_run(store, run_id: str = "sec-run") -> None:
    store.create_run(
        Run(
            id=run_id,
            name="sec",
            task_type=TaskType.CUSTOM,
            started_at=datetime.now(tz=timezone.utc),
            primary_metric="val_loss",
            parser_used="test",
        )
    )


def test_docs_hidden_by_default() -> None:
    """Swagger UI / OpenAPI schema must not be reachable on default settings."""
    app = create_app(settings=Settings(db=":memory:"))
    with TestClient(app) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/redoc").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404


def test_docs_visible_when_auth_token_set() -> None:
    """Operators with auth configured see the docs (behind the same auth)."""
    app = create_app(settings=Settings(db=":memory:", auth_token="t"))
    with TestClient(app) as client:
        assert client.get("/api/docs").status_code == 200
        assert client.get("/api/openapi.json").status_code == 200


def test_docs_visible_when_explicitly_enabled() -> None:
    app = create_app(settings=Settings(db=":memory:", expose_docs=True))
    with TestClient(app) as client:
        assert client.get("/api/docs").status_code == 200


def test_no_cors_middleware_by_default() -> None:
    """An Origin header from a cross-site page must NOT echo back."""
    app = create_app(settings=Settings(db=":memory:"))
    with TestClient(app) as client:
        r = client.get("/api/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_cors_enabled_when_origins_configured() -> None:
    app = create_app(settings=Settings(db=":memory:", cors_origins="https://app.example.com"))
    with TestClient(app) as client:
        r = client.get("/api/health", headers={"Origin": "https://app.example.com"})
        assert r.headers.get("access-control-allow-origin") == "https://app.example.com"


def test_destructive_rejected_from_non_loopback_without_token() -> None:
    """A remote caller without a Bearer token cannot delete or push events."""
    app = create_app(settings=Settings(db=":memory:"))
    # Simulate a non-loopback remote client (e.g. another host on the LAN).
    with TestClient(app, client=("203.0.113.7", 12345)) as client:
        _make_run(app.state.store, "victim")
        r_delete = client.delete("/api/runs/victim")
        assert r_delete.status_code == 401
        # The run still exists.
        assert app.state.store.get_run("victim") is not None

        r_event = client.post(
            "/api/runs/victim/event",
            json={
                "seq": 1,
                "canonical_key": "val_loss",
                "raw_key": "val_loss",
                "value": 0.5,
            },
        )
        assert r_event.status_code == 401


def test_destructive_allowed_from_loopback_without_token() -> None:
    """Local CLI/SDK usage stays zero-config: same-machine writes are admitted."""
    app = create_app(settings=Settings(db=":memory:"))
    with TestClient(app) as client:  # default client = "testclient" (loopback-equiv)
        _make_run(app.state.store, "local-run")
        r = client.delete("/api/runs/local-run")
        assert r.status_code == 200
        assert app.state.store.get_run("local-run") is None


def test_destructive_remote_with_valid_token_allowed() -> None:
    """A remote caller WITH a correct Bearer token may delete."""
    app = create_app(settings=Settings(db=":memory:", auth_token="s3cret"))
    with TestClient(app, client=("203.0.113.7", 12345)) as client:
        _make_run(app.state.store, "remote-run")
        r = client.delete(
            "/api/runs/remote-run",
            headers={"Authorization": "Bearer s3cret"},
        )
        assert r.status_code == 200


def test_event_push_rejects_oversized_strings() -> None:
    """Field length caps prevent DB-bloat via huge canonical_key."""
    app = create_app(settings=Settings(db=":memory:"))
    with TestClient(app) as client:
        _make_run(app.state.store, "oversize-run")
        r = client.post(
            "/api/runs/oversize-run/event",
            json={
                "seq": 1,
                "canonical_key": "x" * 1000,
                "raw_key": "x",
                "value": 0.5,
            },
        )
        assert r.status_code == 422  # pydantic validation failure
