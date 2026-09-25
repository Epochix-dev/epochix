"""Catch up with the schema the store has been creating.

The store builds its tables from SQLAlchemy metadata and backfills columns
itself, so nothing ran these migrations and they fell behind: the milestones
and raw_lines tables, and story_frames' primary_key and task_type columns,
existed only in the store. tests/unit/test_migrations_match_schema.py now fails
when the two disagree.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "milestones",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("epoch", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id", "seq", "kind"),
    )
    op.create_table(
        "raw_lines",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )
    with op.batch_alter_table("story_frames") as batch:
        batch.add_column(sa.Column("primary_key", sa.String(), nullable=True))
        batch.add_column(sa.Column("task_type", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.drop_column("task_type")
        batch.drop_column("primary_key")
    op.drop_table("raw_lines")
    op.drop_table("milestones")
