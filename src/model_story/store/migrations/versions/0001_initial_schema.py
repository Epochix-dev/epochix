"""Initial schema — runs, metric_events, story_frames.

Revision ID: 0001
Revises:
Create Date: 2026-05-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), nullable=False, primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("primary_metric", sa.String(), nullable=False),
        sa.Column("framework", sa.String(), nullable=True),
        sa.Column("parser_used", sa.String(), nullable=True),
        sa.Column("total_epochs", sa.Integer(), nullable=True),
        sa.Column("final_grade", sa.String(), nullable=True),
        sa.Column("story_summary", sa.Text(), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "metric_events",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("epoch", sa.Float(), nullable=True),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("canonical_key", sa.String(), nullable=False),
        sa.Column("raw_key", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )
    op.create_index("idx_metric_run_epoch", "metric_events", ["run_id", "epoch"])
    op.create_index("idx_metric_run_key", "metric_events", ["run_id", "canonical_key"])

    op.create_table(
        "story_frames",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("epoch", sa.Float(), nullable=True),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("phase", sa.String(), nullable=True),
        sa.Column("grade", sa.String(), nullable=True),
        sa.Column("primary_value", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("metaphor_json", sa.Text(), nullable=True),
        sa.Column("skill_json", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id", "seq"),
    )


def downgrade() -> None:
    op.drop_table("story_frames")
    op.drop_index("idx_metric_run_key", table_name="metric_events")
    op.drop_index("idx_metric_run_epoch", table_name="metric_events")
    op.drop_table("metric_events")
    op.drop_table("runs")
