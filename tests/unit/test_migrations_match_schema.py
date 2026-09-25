"""The Alembic migrations build the schema the store actually uses.

The store creates its tables from SQLAlchemy metadata and backfills new
columns itself; nothing ran the migrations, so they drifted unnoticed —
`story_frames.primary_key` was added to the store and never to a migration.
Whoever runs `alembic upgrade head` (a hosted deployment, one day) must get the
same tables, or the first frame written fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from epochix.store.sqlite_store import metadata

alembic = pytest.importorskip("alembic")  # a dev dependency; CI has it

ROOT = Path(__file__).resolve().parents[2]


def _columns(url: str) -> dict[str, set[str]]:
    insp = inspect(create_engine(url))
    return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}


def test_alembic_head_matches_the_store(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    migrated = f"sqlite:///{tmp_path / 'migrated.db'}"
    # No ini file: env.py would run logging.config.fileConfig on it, which
    # disables every existing logger for the rest of the test session.
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "src" / "epochix" / "store" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", migrated)
    command.upgrade(cfg, "head")

    created = f"sqlite:///{tmp_path / 'created.db'}"
    metadata.create_all(create_engine(created))

    want = _columns(created)
    got = {t: cols for t, cols in _columns(migrated).items() if t != "alembic_version"}
    assert set(got) == set(want), f"tables differ: {set(got) ^ set(want)}"
    for table, cols in want.items():
        assert got[table] == cols, (
            f"{table}: missing {cols - got[table]}, extra {got[table] - cols}"
        )
