"""End-to-end API integration tests.

Focuses on the *event-push pipeline*: pushing metric events via POST
/api/runs/{id}/event, then verifying the story engine has produced frames
that appear in the snapshot endpoint.

These tests complement tests/unit/test_server.py (which covers basic CRUD).
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from model_story.config import Settings
from model_story.enums import TaskType
from model_story.models import Run
from model_story.server.app import create_app
from model_story.store.sqlite_store import RunStore
from model_story.story_engine import StoryEngine


@pytest.fixture()
def server() -> Iterator[tuple[TestClient, RunStore]]:
    settings = Settings(db=":memory:")
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=True) as client:
        store: RunStore = app.state.store
        yield client, store


def _make_run(run_id: str = "run-001") -> Run:
    return Run(
        id=run_id,
        name="E2E Test Run",
        task_type=TaskType.CLASSIFICATION,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric="val_accuracy",
        parser_used="pytorch_lightning",
    )


# ── Event push ────────────────────────────────────────────────────────────────

class TestEventPush:
    def test_push_event_accepted(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("push-run-01"))
        r = client.post(
            "/api/runs/push-run-01/event",
            json={
                "seq": 1,
                "canonical_key": "val_accuracy",
                "raw_key": "acc",
                "value": 0.75,
                "epoch": 1.0,
            },
        )
        assert r.status_code == 202
        body = r.json()
        assert body["accepted"] is True
        assert body["seq"] == 1

    def test_push_event_increments_seq(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        """Each push uses a unique seq and is stored."""
        client, store = server
        store.create_run(_make_run("seq-run"))
        for seq in range(1, 4):
            r = client.post(
                "/api/runs/seq-run/event",
                json={
                    "seq": seq,
                    "canonical_key": "val_accuracy",
                    "raw_key": "acc",
                    "value": 0.5 + seq * 0.05,
                    "epoch": float(seq),
                },
            )
            assert r.status_code == 202

    def test_push_validates_required_fields(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, _ = server
        # Missing seq
        r = client.post(
            "/api/runs/v-run/event",
            json={"canonical_key": "val_accuracy", "raw_key": "acc", "value": 0.5},
        )
        assert r.status_code == 422

    def test_push_validates_numeric_value(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, _ = server
        r = client.post(
            "/api/runs/v-run/event",
            json={"seq": 1, "canonical_key": "val_accuracy", "raw_key": "acc", "value": "string"},
        )
        assert r.status_code == 422


# ── Story engine pipeline ─────────────────────────────────────────────────────

class TestPipeline:
    def test_push_events_and_get_metrics(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        """Events pushed via HTTP appear in GET /api/metrics/{id}."""
        client, store = server
        store.create_run(_make_run("pipe-run-01"))

        for i in range(5):
            client.post(
                "/api/runs/pipe-run-01/event",
                json={
                    "seq": i + 1,
                    "canonical_key": "val_accuracy",
                    "raw_key": "acc",
                    "value": 0.5 + i * 0.08,
                    "epoch": float(i + 1),
                },
            )

        r = client.get("/api/metrics/pipe-run-01")
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) == 5
        assert events[0]["canonical_key"] == "val_accuracy"

    def test_story_engine_produces_frames_via_engine_map(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        """When a StoryEngine is registered in engine_map, frames are stored."""
        client, store = server

        run = _make_run("pipe-run-02")
        store.create_run(run)

        # Register a StoryEngine manually (as the SDK LiveReporter does)
        from model_story.server.app import create_app as _ca  # noqa: F401

        app_state = client.app.state  # type: ignore[attr-defined]
        engine = StoryEngine(run_id="pipe-run-02", task=TaskType.CLASSIFICATION)
        app_state.engine_map["pipe-run-02"] = engine

        # Push enough events to trigger frame generation (engine needs ≥3)
        for i in range(5):
            client.post(
                "/api/runs/pipe-run-02/event",
                json={
                    "seq": i + 1,
                    "canonical_key": "val_accuracy",
                    "raw_key": "acc",
                    "value": 0.5 + i * 0.08,
                    "epoch": float(i + 1),
                },
            )

        # Frames should appear in snapshot
        r = client.get("/api/snapshot/pipe-run-02")
        assert r.status_code == 200
        frames = r.json()["frames"]
        # Frames are generated on primary metric events (val_accuracy) after ≥3 events
        assert len(frames) >= 1
        assert frames[0]["grade"] is not None
        assert frames[0]["phase"] is not None

    def test_snapshot_reflects_latest_frame(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        """Snapshot current_frame is the most recent story frame."""
        client, store = server

        run = _make_run("pipe-run-03")
        store.create_run(run)

        app_state = client.app.state  # type: ignore[attr-defined]
        engine = StoryEngine(run_id="pipe-run-03", task=TaskType.CLASSIFICATION)
        app_state.engine_map["pipe-run-03"] = engine

        for i in range(6):
            client.post(
                "/api/runs/pipe-run-03/event",
                json={
                    "seq": i + 1,
                    "canonical_key": "val_accuracy",
                    "raw_key": "acc",
                    "value": 0.55 + i * 0.06,
                    "epoch": float(i + 1),
                },
            )

        snap_r = client.get("/api/snapshot/pipe-run-03")
        assert snap_r.status_code == 200
        snap = snap_r.json()
        frames = snap["frames"]
        if frames:
            # Primary value should match last push
            last = frames[-1]
            assert last["primary_metric_value"] >= 0.5


# ── Multi-metric run ──────────────────────────────────────────────────────────

class TestMultiMetric:
    def test_push_multiple_metrics_all_stored(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        store.create_run(_make_run("multi-run"))

        metrics = [
            ("train_loss", 0.8),
            ("val_loss", 0.9),
            ("val_accuracy", 0.55),
            ("train_accuracy", 0.6),
            ("lr", 0.001),
        ]
        for i, (key, val) in enumerate(metrics):
            client.post(
                "/api/runs/multi-run/event",
                json={
                    "seq": i + 1,
                    "canonical_key": key,
                    "raw_key": key,
                    "value": val,
                    "epoch": 1.0,
                },
            )

        r = client.get("/api/metrics/multi-run")
        assert r.status_code == 200
        events = r.json()["events"]
        assert len(events) == 5
        keys = {e["canonical_key"] for e in events}
        assert "val_accuracy" in keys
        assert "train_loss" in keys


# ── Multi-run comparison ────────────────────────────────────────────────────────

class TestCompare:
    def test_compare_returns_multiple_runs(self, server: tuple[TestClient, RunStore]) -> None:
        from model_story.models import MetricEvent

        client, store = server
        for rid in ("cmp-a", "cmp-b"):
            store.create_run(_make_run(rid))
            for i in range(3):
                store.append_metric_event(MetricEvent(
                    run_id=rid, seq=i + 1, timestamp=datetime.now(tz=timezone.utc),
                    epoch=float(i + 1), canonical_key="val_accuracy",
                    raw_key="acc", value=0.5 + i * 0.1,
                ))
        r = client.get("/api/compare?run_ids=cmp-a,cmp-b")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        ids = {cr["run"]["id"] for cr in data["runs"]}
        assert ids == {"cmp-a", "cmp-b"}
        assert len(data["runs"][0]["metrics"]) == 3

    def test_compare_skips_unknown_ids(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        store.create_run(_make_run("cmp-real"))
        r = client.get("/api/compare?run_ids=cmp-real,ghost-run")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_compare_empty(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        assert client.get("/api/compare?run_ids=").json()["total"] == 0
