"""Server integration tests — REST API using FastAPI TestClient."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from epochix.config import Settings
from epochix.enums import TaskType
from epochix.models import Run
from epochix.server.app import create_app
from epochix.store.sqlite_store import RunStore


@pytest.fixture()
def server() -> Iterator[tuple[TestClient, RunStore]]:
    """Start the full app (lifespan included) with an in-memory store.

    Yields ``(client, store)`` so tests can pre-populate the DB before
    making HTTP requests.
    """
    settings = Settings(db=":memory:")
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=True) as client:
        store: RunStore = app.state.store
        yield client, store


def _make_run(run_id: str = "run-001") -> Run:
    return Run(
        id=run_id,
        name="Test Run",
        task_type=TaskType.CLASSIFICATION,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric="val_accuracy",
        parser_used="keras_tensorflow",
    )


class TestHealthVersion:
    def test_health(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_version(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.get("/api/version")
        assert r.status_code == 200
        assert "version" in r.json()


class TestRunsCRUD:
    def test_list_runs_empty(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.get("/api/runs")
        assert r.status_code == 200
        data = r.json()
        assert data["runs"] == []
        assert data["total"] == 0

    def test_create_and_get_run(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("abc-123"))
        r = client.get("/api/runs/abc-123")
        assert r.status_code == 200
        assert r.json()["id"] == "abc-123"

    def test_get_run_not_found(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.get("/api/runs/does-not-exist")
        assert r.status_code == 404

    def test_list_runs_returns_created(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("r1"))
        store.create_run(_make_run("r2"))
        r = client.get("/api/runs")
        assert r.status_code == 200
        assert r.json()["total"] == 2

    def test_delete_run(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("del-me"))
        r = client.delete("/api/runs/del-me")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        assert client.get("/api/runs/del-me").status_code == 404

    def test_delete_run_not_found(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.delete("/api/runs/ghost")
        assert r.status_code == 404


class TestSnapshotEndpoints:
    def test_snapshot_empty(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("snap-run"))
        r = client.get("/api/snapshot/snap-run")
        assert r.status_code == 200
        data = r.json()
        assert data["run_id"] == "snap-run"
        assert data["frames"] == []

    def test_metrics_empty(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("met-run"))
        r = client.get("/api/metrics/met-run")
        assert r.status_code == 200
        assert r.json()["events"] == []

    def test_snapshot_not_found(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.get("/api/snapshot/ghost")
        assert r.status_code == 404


class TestExportEndpoints:
    def test_html_export_returns_501_when_bundle_not_built(
        self, server: tuple[TestClient, RunStore], monkeypatch
    ) -> None:
        # 501 when the Vite bundle hasn't been built yet. Force the missing-bundle
        # condition so the test is deterministic regardless of build state.
        import epochix.server.routes_export as rex

        def _no_bundle(**_kwargs: object) -> str:
            raise FileNotFoundError("frontend bundle not built")

        monkeypatch.setattr(rex, "build_html", _no_bundle)
        client, store = server
        store.create_run(_make_run("exp-run"))
        r = client.get("/api/export/exp-run/html")
        assert r.status_code == 501

    def test_json_export_returns_valid_json(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        store.create_run(_make_run("json-run"))
        r = client.get("/api/export/json-run/json")
        assert r.status_code == 200
        data = r.json()
        assert data["run"]["id"] == "json-run"
        assert "frames" in data
        assert "events" in data

    def test_export_not_found(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        r = client.get("/api/export/ghost/json")
        assert r.status_code == 404
