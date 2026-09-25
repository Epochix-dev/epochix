"""story_frames.grade_note: why a frame's letter deserves less weight.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.add_column(sa.Column("grade_note", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.drop_column("grade_note")
