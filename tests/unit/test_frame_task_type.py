"""A stored frame keeps the task it was told under.

The frames table had no task column, so every frame read back as CUSTOM
whatever the run was — the JSON export, the snapshot and compare APIs, and the
Markdown/PDF/GIF exporters all saw a regression run's frames as "custom".
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from epochix.enums import Grade, Phase, TaskType
from epochix.models import Run, StoryFrame
from epochix.store.sqlite_store import RunStore


def _run(run_id: str, task: TaskType) -> Run:
    return Run(
        id=run_id,
        task_type=task,
        started_at=datetime.now(tz=timezone.utc),
        primary_metric="MAE",
        parser_used="universal",
    )


def _frame(run_id: str, seq: int, task: TaskType) -> StoryFrame:
    return StoryFrame(
        run_id=run_id,
        seq=seq,
        epoch=float(seq),
        progress=0.1,
        phase=Phase.LEARNING,
        grade=Grade.B,
        primary_metric_value=1.5,
        primary_metric="MAE",
        confidence=0.5,
        narrative="x",
        task_type=task,
    )


def test_frames_read_back_with_their_task(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "runs.db"))
    store.create_run(_run("r", TaskType.REGRESSION))
    store.append_story_frame(_frame("r", 1, TaskType.CUSTOM))  # before detection
    store.append_story_frame(_frame("r", 2, TaskType.REGRESSION))
    assert [f.task_type for f in store.get_story_frames("r")] == [
        TaskType.CUSTOM,
        TaskType.REGRESSION,
    ]


def test_a_database_from_before_the_column_is_upgraded_in_place(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    store = RunStore(str(db))
    store.create_run(_run("old", TaskType.REGRESSION))
    store.append_story_frame(_frame("old", 1, TaskType.REGRESSION))
    del store

    # Rebuild story_frames as it was before the column existed.
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE sf_old AS SELECT run_id, seq, epoch, progress, phase, grade,
            primary_value, primary_key, confidence, narrative, metaphor_json,
            skill_json, warnings_json FROM story_frames;
        DROP TABLE story_frames;
        ALTER TABLE sf_old RENAME TO story_frames;
        """
    )
    con.commit()
    con.close()

    reopened = RunStore(str(db))
    columns = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(story_frames)")}
    assert "task_type" in columns, "the column was not added to an existing database"
    # A frame written before the column existed takes the run's task, not CUSTOM.
    assert [f.task_type for f in reopened.get_story_frames("old")] == [TaskType.REGRESSION]
