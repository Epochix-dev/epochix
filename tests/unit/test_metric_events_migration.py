"""The metric_events primary-key migration, against a real legacy database.

This migration rewrites a table in databases that already exist on users'
machines, and until now nothing exercised it. The bug it repairs is the one
that makes it worth testing: the pre-0.1 schema keyed on ``(run_id, seq)``
alone, so the several metrics emitted on one log line — loss, acc, val_loss —
collided, and every one after the first was dropped on insert.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from epochix.store.sqlite_store import RunStore

# The pre-0.1 schema, verbatim in shape: primary key on (run_id, seq) only.
_LEGACY_DDL = (
    "CREATE TABLE metric_events ("
    " run_id TEXT NOT NULL,"
    " seq INTEGER NOT NULL,"
    " canonical_key TEXT NOT NULL,"
    " ts TIMESTAMP NOT NULL,"
    " epoch FLOAT, step INTEGER,"
    " raw_key TEXT NOT NULL, value FLOAT NOT NULL, unit TEXT,"
    " PRIMARY KEY (run_id, seq))"
)

# One row per (run_id, seq) — the legacy schema physically cannot hold more,
# which *is* the bug: the second and third metric on a log line were rejected
# at write time and lost. The migration cannot recover them; what it must do
# is preserve what survived and widen the key so new writes stop colliding.
_ROWS = [
    ("r1", 1, "loss", "2024-01-01 00:00:00", 1.0, None, "loss", 0.5, None),
    ("r1", 2, "loss", "2024-01-01 00:00:01", 2.0, None, "loss", 0.4, None),
    ("r1", 3, "loss", "2024-01-01 00:00:02", 3.0, None, "loss", 0.3, None),
]


def _legacy_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")
    con.execute("INSERT INTO runs (id) VALUES ('r1')")
    con.execute(_LEGACY_DDL)
    con.executemany("INSERT INTO metric_events VALUES (?,?,?,?,?,?,?,?,?)", _ROWS)
    con.commit()
    con.close()


def test_migration_preserves_every_row(tmp_path: Path) -> None:
    """Opening a legacy database must rebuild the table without losing rows."""
    db = tmp_path / "legacy.db"
    _legacy_db(db)

    RunStore(str(db))  # migration runs in __init__

    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT run_id, seq, canonical_key, value FROM metric_events ORDER BY seq, canonical_key"
        ).fetchall()
        pk = {r[1] for r in con.execute("PRAGMA table_info(metric_events)") if r[5]}
        leftover = con.execute(
            "SELECT name FROM sqlite_master WHERE name='_metric_events_old'"
        ).fetchall()
    finally:
        con.close()

    assert "canonical_key" in pk, "primary key was not widened"
    assert not leftover, "the temporary migration table was left behind"
    assert rows == [
        ("r1", 1, "loss", 0.5),
        ("r1", 2, "loss", 0.4),
        ("r1", 3, "loss", 0.3),
    ]


def test_migration_lets_one_line_write_several_metrics(tmp_path: Path) -> None:
    """The point of the migration: after it, a shared seq no longer collides.

    Before, loss/accuracy/val_loss emitted on one log line shared (run_id, seq)
    and all but the first were silently dropped. If this insert raises, the key
    was not actually widened and the original data-loss bug is back.
    """
    db = tmp_path / "legacy.db"
    _legacy_db(db)
    RunStore(str(db))

    con = sqlite3.connect(db)
    try:
        con.executemany(
            "INSERT INTO metric_events VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("r1", 9, "loss", "2024-01-01 00:00:09", 9.0, None, "loss", 0.2, None),
                ("r1", 9, "accuracy", "2024-01-01 00:00:09", 9.0, None, "acc", 0.9, None),
                ("r1", 9, "val_loss", "2024-01-01 00:00:09", 9.0, None, "val_loss", 0.25, None),
            ],
        )
        con.commit()
        got = con.execute("SELECT count(*) FROM metric_events WHERE seq=9").fetchone()[0]
    finally:
        con.close()
    assert got == 3, "metrics sharing a seq were dropped — the composite key is not in effect"


def test_migration_is_idempotent(tmp_path: Path) -> None:
    """Re-opening an already-migrated database must be a no-op, not a rebuild."""
    db = tmp_path / "legacy.db"
    _legacy_db(db)

    RunStore(str(db))
    RunStore(str(db))  # second open: must not raise or drop anything

    con = sqlite3.connect(db)
    try:
        count = con.execute("SELECT count(*) FROM metric_events").fetchone()[0]
    finally:
        con.close()
    assert count == len(_ROWS)


def test_fresh_database_needs_no_migration(tmp_path: Path) -> None:
    """A brand-new database already has the composite key."""
    store = RunStore(str(tmp_path / "fresh.db"))
    assert store is not None

    con = sqlite3.connect(tmp_path / "fresh.db")
    try:
        pk = {r[1] for r in con.execute("PRAGMA table_info(metric_events)") if r[5]}
    finally:
        con.close()
    assert "canonical_key" in pk
