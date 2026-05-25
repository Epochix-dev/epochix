"""SQLite store unit tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from model_story.enums import Grade, TaskType
from model_story.models import MetricEvent, Run
from model_story.store.sqlite_store import RunStore


@pytest.fixture
def store() -> RunStore:
    return RunStore(":memory:")


def _make_run(run_id: str = "run-1") -> Run:
    return Run(
        id=run_id,
        name="test run",
        task_type=TaskType.CLASSIFICATION,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric="val_accuracy",
        parser_used="pytorch_lightning",
    )


def _make_event(run_id: str, seq: int, value: float) -> MetricEvent:
    return MetricEvent(
        run_id=run_id,
        seq=seq,
        timestamp=datetime.now(tz=timezone.utc),
        epoch=float(seq),
        canonical_key="val_accuracy",
        raw_key="val_acc",
        value=value,
    )


class TestRunStore:
    def test_create_and_get_run(self, store: RunStore) -> None:
        run = _make_run()
        store.create_run(run)
        fetched = store.get_run("run-1")
        assert fetched is not None
        assert fetched.id == "run-1"
        assert fetched.task_type == TaskType.CLASSIFICATION

    def test_list_runs(self, store: RunStore) -> None:
        for i in range(3):
            store.create_run(_make_run(f"run-{i}"))
        runs = store.list_runs()
        assert len(runs) == 3

    def test_delete_run(self, store: RunStore) -> None:
        store.create_run(_make_run())
        store.delete_run("run-1")
        assert store.get_run("run-1") is None

    def test_append_and_get_metric_events(self, store: RunStore) -> None:
        store.create_run(_make_run())
        for i in range(5):
            store.append_metric_event(_make_event("run-1", i, 0.5 + i * 0.05))
        events = store.get_metric_events("run-1")
        assert len(events) == 5
        assert events[-1].value == pytest.approx(0.70)

    def test_idempotent_append(self, store: RunStore) -> None:
        store.create_run(_make_run())
        ev = _make_event("run-1", 0, 0.5)
        store.append_metric_event(ev)
        store.append_metric_event(ev)  # duplicate — should be ignored
        events = store.get_metric_events("run-1")
        assert len(events) == 1

    def test_finish_run(self, store: RunStore) -> None:
        store.create_run(_make_run())
        store.finish_run("run-1", final_grade=Grade.A, story_summary="Well done.")
        run = store.get_run("run-1")
        assert run is not None
        assert run.final_grade == Grade.A
        assert run.story_summary == "Well done."
