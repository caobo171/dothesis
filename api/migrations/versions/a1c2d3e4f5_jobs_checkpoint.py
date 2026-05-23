"""add checkpoint_json and completed_phase to jobs

Revision ID: a1c2d3e4f501
Revises: 3e096aa7ea23
Create Date: 2026-05-23 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1c2d3e4f501"
down_revision: Union[str, None] = "3e096aa7ea23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("checkpoint_json", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("completed_phase", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "completed_phase")
    op.drop_column("jobs", "checkpoint_json")
