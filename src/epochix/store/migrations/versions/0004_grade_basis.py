"""story_frames.grade_basis: how a frame's letter was reached.

"thresholds" or "improvement", or NULL where there is no letter to explain.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.add_column(sa.Column("grade_basis", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.drop_column("grade_basis")
