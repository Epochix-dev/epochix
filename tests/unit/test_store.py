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


# ── Multiple metrics per log-line seq + legacy DB auto-migration ───────────────

def test_multiple_metrics_same_seq_all_stored(store: RunStore) -> None:
    """Several canonical keys sharing one seq (one log line) must all persist."""
    store.create_run(_make_run("multi"))
    now = datetime.now(tz=timezone.utc)
    for key, raw, val in [("train_loss", "loss", 0.4), ("accuracy", "acc", 0.8),
                          ("val_loss", "val_loss", 0.5), ("val_accuracy", "val_acc", 0.78)]:
        store.append_metric_event(MetricEvent(
            run_id="multi", seq=7, timestamp=now, epoch=7.0,
            canonical_key=key, raw_key=raw, value=val,
        ))
    keys = sorted({e.canonical_key for e in store.get_metric_events("multi")})
    assert keys == ["accuracy", "train_loss", "val_accuracy", "val_loss"]


def test_legacy_db_metric_events_pk_is_migrated(tmp_path) -> None:
    """Opening a pre-0.1 DB (PK without canonical_key) rebuilds the table."""
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE runs (id TEXT PRIMARY KEY, name TEXT, task_type TEXT NOT NULL,
          started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP, primary_metric TEXT NOT NULL,
          framework TEXT, parser_used TEXT, total_epochs INTEGER, final_grade TEXT,
          story_summary TEXT, config_json TEXT);
        CREATE TABLE metric_events (run_id TEXT NOT NULL, seq INTEGER NOT NULL,
          ts TIMESTAMP NOT NULL, epoch FLOAT, step INTEGER, canonical_key TEXT NOT NULL,
          raw_key TEXT NOT NULL, value FLOAT NOT NULL, unit TEXT,
          PRIMARY KEY (run_id, seq), FOREIGN KEY(run_id) REFERENCES runs(id));
        CREATE TABLE story_frames (run_id TEXT NOT NULL, seq INTEGER NOT NULL, PRIMARY KEY(run_id,seq));
        CREATE TABLE milestones (run_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(run_id,seq,kind));
        CREATE TABLE raw_lines (run_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TIMESTAMP NOT NULL, text TEXT NOT NULL, PRIMARY KEY(run_id,seq));
        """
    )
    conn.execute(
        "INSERT INTO runs (id, task_type, started_at, primary_metric) VALUES (?,?,?,?)",
        ("r1", "custom", datetime.now(tz=timezone.utc).isoformat(), "val_loss"),
    )
    conn.execute(
        "INSERT INTO metric_events VALUES (?,?,?,?,?,?,?,?,?)",
        ("r1", 1, datetime.now(tz=timezone.utc).isoformat(), 1.0, None, "train_loss", "loss", 0.9, None),
    )
    conn.commit()
    conn.close()

    store = RunStore(db_path=str(db))  # triggers auto-migration

    chk = sqlite3.connect(db)
    pk = sorted(r[1] for r in chk.execute("PRAGMA table_info(metric_events)") if r[5])
    chk.close()
    assert "canonical_key" in pk
    # legacy row preserved
    assert len(store.get_metric_events("r1")) == 1
    # and the multi-metric bug is now fixed for the upgraded DB
    now = datetime.now(tz=timezone.utc)
    for key, raw in [("train_loss", "loss"), ("accuracy", "acc")]:
        store.append_metric_event(MetricEvent(
            run_id="r1", seq=2, timestamp=now, epoch=2.0,
            canonical_key=key, raw_key=raw, value=0.5,
        ))
    assert len({e.canonical_key for e in store.get_metric_events("r1") if e.seq == 2}) == 2
