"""story_frames.counter: what the number in a frame's epoch slot counts.

"epoch", "step", "iteration" or "round"; NULL where the slot is empty, and on
every frame stored before this was recorded.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.add_column(sa.Column("counter", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("story_frames") as batch:
        batch.drop_column("counter")
