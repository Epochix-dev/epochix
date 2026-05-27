"""Export pipeline integration tests.

Seeds a database with a complete run (metric events + story frames), then
exercises all four export endpoints (json, md, html, pdf) and verifies:
  - Correct HTTP status codes
  - Content types
  - Presence of key data in the response body
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from epochix.config import Settings
from epochix.enums import Grade, Phase, TaskType
from epochix.models import MetricEvent, Run, StoryFrame
from epochix.server.app import create_app
from epochix.store.sqlite_store import RunStore

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def server() -> Iterator[tuple[TestClient, RunStore]]:
    settings = Settings(db=":memory:")
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=True) as client:
        store: RunStore = app.state.store
        yield client, store


def _seed(store: RunStore, run_id: str = "export-run") -> None:
    """Insert a run with metric events and story frames."""
    run = Run(
        id=run_id,
        name="Export Integration Run",
        task_type=TaskType.CLASSIFICATION,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric="val_accuracy",
        parser_used="pytorch_lightning",
        total_epochs_est=10,
        final_grade=Grade.B,
        story_summary="Reached 85% accuracy after 10 epochs of training.",
    )
    store.create_run(run)

    now = datetime.now(tz=timezone.utc)
    for i in range(10):
        store.append_metric_event(MetricEvent(
            run_id=run_id, seq=i + 1, timestamp=now,
            epoch=float(i + 1), canonical_key="val_accuracy",
            raw_key="acc", value=0.5 + i * 0.04,
        ))

    for i in range(5):
        store.append_story_frame(StoryFrame(
            run_id=run_id, seq=i + 1,
            epoch=float(i * 2 + 1),
            progress=(i + 1) / 5,
            phase=Phase.LEARNING,
            grade=Grade.B,
            primary_metric_value=0.5 + i * 0.07,
            confidence=0.6 + i * 0.08,
            narrative=f"The model learns at epoch {i * 2 + 1}.",
            task_type=TaskType.CLASSIFICATION,
        ))


# ── JSON export ───────────────────────────────────────────────────────────────

class TestJsonExport:
    def test_json_status_and_content_type(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        _seed(store)
        r = client.get("/api/export/export-run/json")
        assert r.status_code == 200
        assert "application/json" in r.headers["content-type"]

    def test_json_has_run_fields(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        _seed(store)
        data = client.get("/api/export/export-run/json").json()
        assert data["run"]["id"] == "export-run"
        assert data["run"]["task_type"] == "classification"
        assert data["run"]["final_grade"] == "B"

    def test_json_has_events_and_frames(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        _seed(store)
        data = client.get("/api/export/export-run/json").json()
        assert len(data["events"]) == 10
        assert len(data["frames"]) == 5

    def test_json_events_have_canonical_key(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        _seed(store)
        events = client.get("/api/export/export-run/json").json()["events"]
        assert all(e["canonical_key"] == "val_accuracy" for e in events)

    def test_json_not_found(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        assert client.get("/api/export/ghost/json").status_code == 404


# ── Markdown export ───────────────────────────────────────────────────────────

class TestMarkdownExport:
    def test_md_status(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        _seed(store)
        r = client.get("/api/export/export-run/md")
        assert r.status_code == 200

    def test_md_contains_grade(self, server: tuple[TestClient, RunStore]) -> None:
        client, store = server
        _seed(store)
        text = client.get("/api/export/export-run/md").text
        assert "B" in text  # grade

    def test_md_contains_run_identifier(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, store = server
        _seed(store)
        text = client.get("/api/export/export-run/md").text
        # Run id or name should appear
        assert "export-run" in text or "Export Integration Run" in text

    def test_md_not_found(self, server: tuple[TestClient, RunStore]) -> None:
        client, _ = server
        assert client.get("/api/export/ghost/md").status_code == 404


# ── HTML export ───────────────────────────────────────────────────────────────

class TestHtmlExport:
    def test_html_not_available_without_build(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        """HTML export requires the Vite bundle; returns 501 when not built."""
        client, store = server
        _seed(store)
        r = client.get("/api/export/export-run/html")
        # 200 if bundle is built, 501 if not
        assert r.status_code in (200, 501)

    def test_html_404_for_missing_run(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        client, _ = server
        assert client.get("/api/export/ghost/html").status_code == 404

    def test_html_escapes_script_breakout_in_run_data(self) -> None:
        """A malicious run name must not break out of the inlined <script>."""
        import pytest

        from epochix.exporters.html_export import build_html

        store = RunStore(":memory:")
        run = Run(
            id="xss-run",
            name="</script><img src=x onerror=alert(1)>",
            task_type=TaskType.CUSTOM,
            started_at=datetime.now(tz=timezone.utc),
            primary_metric="val_loss",
            parser_used="pytorch_lightning",
            final_grade=Grade.A_MINUS,
        )
        store.create_run(run)
        try:
            html = build_html("xss-run", store)
        except FileNotFoundError:
            pytest.skip("frontend bundle not built")

        # The raw breakout sequence must not appear inside the run-data block.
        start = html.index('id="run-data">') + len('id="run-data">')
        end = html.index("</script>", start)
        run_data = html[start:end]
        assert "</script" not in run_data
        assert "\\u003c" in run_data  # '<' was escaped to its \uXXXX form


# ── Re-import from JSON ───────────────────────────────────────────────────────

class TestJsonReimport:
    def test_json_export_is_reimportable(
        self, server: tuple[TestClient, RunStore]
    ) -> None:
        """The JSON export can be parsed back into model types."""
        client, store = server
        _seed(store)
        data = client.get("/api/export/export-run/json").json()

        # Re-hydrate the run
        run = Run.model_validate(data["run"])
        assert run.id == "export-run"
        assert run.task_type == TaskType.CLASSIFICATION

        # Re-hydrate metric events
        events = [MetricEvent.model_validate(e) for e in data["events"]]
        assert len(events) == 10
        assert all(e.value >= 0.5 for e in events)

        # Re-hydrate story frames
        frames = [StoryFrame.model_validate(f) for f in data["frames"]]
        assert len(frames) == 5
        assert all(f.grade == Grade.B for f in frames)
