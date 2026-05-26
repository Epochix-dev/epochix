from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine

from model_story.enums import Grade, TaskType
from model_story.models import MetricEvent, Run, StoryFrame

logger = logging.getLogger(__name__)

metadata = MetaData()

runs_table = Table(
    "runs", metadata,
    Column("id", String, primary_key=True),
    Column("name", String),
    Column("task_type", String, nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime),
    Column("primary_metric", String, nullable=False),
    Column("framework", String),
    Column("parser_used", String),
    Column("total_epochs", Integer),
    Column("final_grade", String),
    Column("story_summary", Text),
    Column("config_json", Text),
)

metric_events_table = Table(
    "metric_events", metadata,
    Column("run_id", String, ForeignKey("runs.id"), nullable=False, primary_key=True),
    Column("seq", Integer, nullable=False, primary_key=True),
    # A single log line often carries several metrics (e.g. loss, acc, val_loss,
    # val_acc) which all share the line's seq. Include the canonical key in the
    # primary key so every metric on a line is stored instead of only the first.
    Column("canonical_key", String, nullable=False, primary_key=True),
    Column("ts", DateTime, nullable=False),
    Column("epoch", Float),
    Column("step", Integer),
    Column("raw_key", String, nullable=False),
    Column("value", Float, nullable=False),
    Column("unit", String),
)

story_frames_table = Table(
    "story_frames", metadata,
    Column("run_id", String, ForeignKey("runs.id"), nullable=False, primary_key=True),
    Column("seq", Integer, nullable=False, primary_key=True),
    Column("epoch", Float),
    Column("progress", Float),
    Column("phase", String),
    Column("grade", String),
    Column("primary_value", Float),
    Column("confidence", Float),
    Column("narrative", Text),
    Column("metaphor_json", Text),
    Column("skill_json", Text),
    Column("warnings_json", Text),
)

milestones_table = Table(
    "milestones", metadata,
    Column("run_id", String, ForeignKey("runs.id"), nullable=False, primary_key=True),
    Column("seq", Integer, nullable=False, primary_key=True),
    Column("kind", String, nullable=False, primary_key=True),
    Column("epoch", Float),
    Column("value", Float),
    Column("message", Text),
)

raw_lines_table = Table(
    "raw_lines", metadata,
    Column("run_id", String, ForeignKey("runs.id"), nullable=False, primary_key=True),
    Column("seq", Integer, nullable=False, primary_key=True),
    Column("ts", DateTime, nullable=False),
    Column("text", Text, nullable=False),
)

Index("idx_metric_run_epoch", metric_events_table.c.run_id, metric_events_table.c.epoch)
Index("idx_metric_run_key", metric_events_table.c.run_id, metric_events_table.c.canonical_key)


def _configure_sqlite(conn: Any, _record: Any) -> None:  # noqa: ANN401
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA journal_size_limit=67108864")  # 64 MB
    conn.execute("PRAGMA foreign_keys=ON")


class RunStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        if db_path == ":memory:":
            # Use StaticPool + check_same_thread=False so the single in-memory
            # database is shared across all threads (required for testing with
            # TestClient, which runs the ASGI app in a separate thread).
            from sqlalchemy.pool import StaticPool

            self._engine: Engine = create_engine(
                "sqlite:///:memory:",
                echo=False,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        event.listen(self._engine, "connect", _configure_sqlite)
        metadata.create_all(self._engine)
        self._heal_metric_events_pk()

    def _heal_metric_events_pk(self) -> None:
        """Upgrade pre-0.1 databases in place.

        Early schemas keyed ``metric_events`` on ``(run_id, seq)`` only, so the
        several metrics emitted on a single log line (loss, acc, val_loss, …)
        collided and all but the first were silently dropped on insert. The
        primary key now includes ``canonical_key``; rebuild the table if an old
        database is opened so existing users get the fix automatically.

        Foreign-key enforcement is disabled for the rebuild (standard SQLite
        table-migration practice) so the copy can't fail on legacy rows.
        """
        new_ddl = (
            "CREATE TABLE metric_events ("
            " run_id TEXT NOT NULL REFERENCES runs(id),"
            " seq INTEGER NOT NULL,"
            " canonical_key TEXT NOT NULL,"
            " ts TIMESTAMP NOT NULL,"
            " epoch FLOAT, step INTEGER,"
            " raw_key TEXT NOT NULL, value FLOAT NOT NULL, unit TEXT,"
            " PRIMARY KEY (run_id, seq, canonical_key))"
        )
        cols = "run_id, seq, ts, epoch, step, canonical_key, raw_key, value, unit"

        raw = self._engine.raw_connection()
        try:
            cur = raw.cursor()
            info = cur.execute("PRAGMA table_info(metric_events)").fetchall()
            if not info:
                return  # table will be created fresh with the correct schema
            pk_cols = {row[1] for row in info if row[5]}  # row[5] = pk position (>0)
            if "canonical_key" in pk_cols:
                return  # already migrated / fresh DB

            logger.info("Migrating metric_events to composite PK (adds canonical_key)…")
            cur.execute("PRAGMA foreign_keys=OFF")
            cur.execute("ALTER TABLE metric_events RENAME TO _metric_events_old")
            cur.execute("DROP INDEX IF EXISTS idx_metric_run_epoch")
            cur.execute("DROP INDEX IF EXISTS idx_metric_run_key")
            cur.execute(new_ddl)
            cur.execute("CREATE INDEX idx_metric_run_epoch ON metric_events (run_id, epoch)")
            cur.execute("CREATE INDEX idx_metric_run_key ON metric_events (run_id, canonical_key)")
            cur.execute(
                f"INSERT OR IGNORE INTO metric_events ({cols}) "
                f"SELECT {cols} FROM _metric_events_old"
            )
            cur.execute("DROP TABLE _metric_events_old")
            raw.commit()
            cur.execute("PRAGMA foreign_keys=ON")
        finally:
            raw.close()

    # ------------------------------------------------------------------ runs

    def create_run(self, run: Run) -> None:
        with self._engine.begin() as conn:
            conn.execute(runs_table.insert(), {
                "id": run.id,
                "name": run.name,
                "task_type": run.task_type.value,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "primary_metric": run.primary_metric,
                "framework": run.framework_detected,
                "parser_used": run.parser_used,
                "total_epochs": run.total_epochs_est,
                "final_grade": run.final_grade.value if run.final_grade else None,
                "story_summary": run.story_summary,
                "config_json": json.dumps(run.config),
            })

    def finish_run(
        self,
        run_id: str,
        final_grade: Grade | None,
        story_summary: str | None,
        finished_at: datetime | None = None,
        task_type: TaskType | None = None,
        parser_used: str | None = None,
        primary_metric: str | None = None,
    ) -> None:
        """Mark a run finished and persist its final summary fields.

        Optional ``task_type`` / ``parser_used`` / ``primary_metric`` overrides
        let the pipeline write back values discovered DURING the run (the
        engine's auto-detected task type, the parser that actually claimed
        the log, the engine's effective primary metric) — without these the
        DB row would keep the placeholder values set at run creation.
        """
        values: dict[str, Any] = {
            "finished_at": finished_at or datetime.now(tz=timezone.utc),
            "final_grade": final_grade.value if final_grade else None,
            "story_summary": story_summary,
        }
        if task_type is not None:
            values["task_type"] = task_type.value
        if parser_used is not None:
            values["parser_used"] = parser_used
        if primary_metric is not None:
            values["primary_metric"] = primary_metric
        with self._engine.begin() as conn:
            conn.execute(
                runs_table.update().where(runs_table.c.id == run_id).values(**values)
            )

    def get_run(self, run_id: str) -> Run | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                runs_table.select().where(runs_table.c.id == run_id)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_run(row)

    def list_runs(self, limit: int = 100) -> list[Run]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                runs_table.select().order_by(runs_table.c.started_at.desc()).limit(limit)
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def update_run_config(self, run_id: str, config: dict[str, Any]) -> None:
        """Persist an updated config dict for a run (e.g. to store architecture)."""
        with self._engine.begin() as conn:
            conn.execute(
                runs_table.update()
                .where(runs_table.c.id == run_id)
                .values(config_json=json.dumps(config))
            )

    def delete_run(self, run_id: str) -> None:
        with self._engine.begin() as conn:
            for tbl in (raw_lines_table, milestones_table, story_frames_table, metric_events_table):
                conn.execute(tbl.delete().where(tbl.c.run_id == run_id))
            conn.execute(runs_table.delete().where(runs_table.c.id == run_id))

    # --------------------------------------------------------- metric events

    def append_metric_event(self, event: MetricEvent) -> None:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        with self._engine.begin() as conn:
            conn.execute(sqlite_insert(metric_events_table).on_conflict_do_nothing(), {
                "run_id": event.run_id,
                "seq": event.seq,
                "ts": event.timestamp,
                "epoch": event.epoch,
                "step": event.step,
                "canonical_key": event.canonical_key,
                "raw_key": event.raw_key,
                "value": event.value,
                "unit": event.unit,
            })

    def get_metric_events(self, run_id: str) -> list[MetricEvent]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                metric_events_table.select()
                .where(metric_events_table.c.run_id == run_id)
                .order_by(metric_events_table.c.seq)
            ).fetchall()
        result = []
        for r in rows:
            result.append(MetricEvent(
                run_id=r.run_id, seq=r.seq,
                timestamp=r.ts if isinstance(r.ts, datetime) else datetime.fromisoformat(str(r.ts)),
                epoch=r.epoch, step=r.step,
                canonical_key=r.canonical_key, raw_key=r.raw_key,
                value=r.value, unit=r.unit,
            ))
        return result

    # ---------------------------------------------------------- story frames

    def append_story_frame(self, frame: StoryFrame) -> None:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        with self._engine.begin() as conn:
            conn.execute(sqlite_insert(story_frames_table).on_conflict_do_nothing(), {
                "run_id": frame.run_id,
                "seq": frame.seq,
                "epoch": frame.epoch,
                "progress": frame.progress,
                "phase": frame.phase.value,
                "grade": frame.grade.value,
                "primary_value": frame.primary_metric_value,
                "confidence": frame.confidence,
                "narrative": frame.narrative,
                "metaphor_json": json.dumps([m.model_dump() for m in frame.metaphor_cards]),
                "skill_json": json.dumps(frame.skill_dimensions),
                "warnings_json": json.dumps([w.model_dump() for w in frame.warnings]),
            })
            for ms in frame.milestones:
                conn.execute(sqlite_insert(milestones_table).on_conflict_do_nothing(), {
                    "run_id": ms.run_id, "seq": ms.seq, "kind": ms.kind,
                    "epoch": ms.epoch, "value": ms.value, "message": ms.message,
                })

    def get_story_frames(self, run_id: str) -> list[StoryFrame]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                story_frames_table.select()
                .where(story_frames_table.c.run_id == run_id)
                .order_by(story_frames_table.c.seq)
            ).fetchall()
        from model_story.enums import Grade, Phase
        from model_story.models import MetaphorCard, Warning
        result = []
        for r in rows:
            result.append(StoryFrame(
                run_id=r.run_id, seq=r.seq, epoch=r.epoch,
                progress=r.progress or 0.0,
                phase=Phase(r.phase),
                grade=Grade(r.grade),
                primary_metric_value=r.primary_value,
                confidence=r.confidence or 0.0,
                narrative=r.narrative or "",
                metaphor_cards=[MetaphorCard(**m) for m in json.loads(r.metaphor_json or "[]")],
                skill_dimensions=json.loads(r.skill_json or "{}"),
                warnings=[Warning(**w) for w in json.loads(r.warnings_json or "[]")],
                milestones=[],
                task_type=TaskType.CUSTOM,  # re-joined when needed
            ))
        return result

    # --------------------------------------------------------------- raw lines

    def append_raw_line(self, run_id: str, seq: int, ts: datetime, text: str) -> None:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        with self._engine.begin() as conn:
            conn.execute(sqlite_insert(raw_lines_table).on_conflict_do_nothing(), {
                "run_id": run_id,
                "seq": seq,
                "ts": ts,
                "text": text,
            })

    def get_raw_lines(self, run_id: str) -> list[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                raw_lines_table.select()
                .where(raw_lines_table.c.run_id == run_id)
                .order_by(raw_lines_table.c.seq)
            ).fetchall()
        return [r.text for r in rows]

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _row_to_run(row: Any) -> Run:  # noqa: ANN401
        return Run(
            id=row.id,
            name=row.name,
            task_type=TaskType(row.task_type),
            started_at=row.started_at if isinstance(row.started_at, datetime)
                        else datetime.fromisoformat(str(row.started_at)),
            finished_at=row.finished_at,
            primary_metric=row.primary_metric,
            framework_detected=row.framework,
            parser_used=row.parser_used or "unknown",
            total_epochs_est=row.total_epochs,
            final_grade=Grade(row.final_grade) if row.final_grade else None,
            story_summary=row.story_summary,
            config=json.loads(row.config_json or "{}"),
        )
