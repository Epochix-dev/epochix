"""Batch parse API — ``from model_story import parse``."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from model_story.enums import TaskType

if TYPE_CHECKING:
    from model_story.models import Run


def parse(
    path: str | Path,
    *,
    task: str | TaskType | None = None,
    primary_metric: str | None = None,
    run_id: str | None = None,
    run_name: str | None = None,
    db: str = ":memory:",
    locale: str = "en",
) -> Run:
    """Parse a training log file and return the completed :class:`~model_story.models.Run`.

    Parameters
    ----------
    path:
        Path to the log file.
    task:
        Force a task type.  Auto-detected when ``None``.
    primary_metric:
        Override the primary metric key.
    run_id:
        Use a specific run ID.  Auto-generated when ``None``.
    run_name:
        Human-readable name for the run.
    db:
        SQLite database path.  Defaults to ``:memory:`` (not persisted).
    locale:
        Language code for narrative templates.

    Returns
    -------
    Run
        Finished run object with ``final_grade`` and ``story_summary``.

    Example
    -------
    ::

        from model_story import parse

        run = parse("train.log", task="biometric")
        print(run.final_grade)   # Grade.A_PLUS
        print(run.story_summary)
    """
    log_path = Path(path)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    effective_task: TaskType | None = (
        TaskType(task) if isinstance(task, str) else task
    )

    try:
        _id = run_id or _gen_id()
    except Exception:  # noqa: BLE001
        import uuid
        _id = str(uuid.uuid4())

    return asyncio.run(
        _parse_async(
            log_path=log_path,
            run_id=_id,
            run_name=run_name,
            task=effective_task,
            primary_metric=primary_metric,
            db=db,
            locale=locale,
        )
    )


async def _parse_async(
    *,
    log_path: Path,
    run_id: str,
    run_name: str | None,
    task: TaskType | None,
    primary_metric: str | None,
    db: str,
    locale: str,
) -> Run:
    from model_story.ingester import make_ingester
    from model_story.pipeline import run_pipeline
    from model_story.server.hub import Hub
    from model_story.store.sqlite_store import RunStore

    store = RunStore(db_path=db)
    hub = Hub()
    ingester = make_ingester(source="file", run_id=run_id, path=str(log_path))

    return await run_pipeline(
        ingester=ingester,
        run_id=run_id,
        store=store,
        hub=hub,
        run_name=run_name,
        task=task,
        primary_metric=primary_metric,
        locale=locale,
    )


def parse_string(
    log_text: str,
    *,
    task: str | TaskType | None = None,
    primary_metric: str | None = None,
    run_id: str | None = None,
    run_name: str | None = None,
    db: str = ":memory:",
    locale: str = "en",
) -> Run:
    """Parse a log string (useful when the log is already in memory).

    Writes *log_text* to a temporary file and delegates to :func:`parse`.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".log", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(log_text)
        tmp = fh.name

    try:
        return parse(
            tmp,
            task=task,
            primary_metric=primary_metric,
            run_id=run_id,
            run_name=run_name,
            db=db,
            locale=locale,
        )
    finally:
        Path(tmp).unlink(missing_ok=True)


def _gen_id() -> str:
    from ulid import ULID

    return str(ULID())
