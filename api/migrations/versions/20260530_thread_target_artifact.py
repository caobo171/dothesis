"""add threads.target_artifact

Revision ID: 20260530_target01
Revises: 20260527_uploads01
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260530_target01"
down_revision = "20260527_uploads01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing threads have no target (normal sequential flow). Set
    # only by POST /projects/{id}/threads/start-at/{artifact} (enter-at-any-step).
    op.add_column(
        "threads",
        sa.Column("target_artifact", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("threads", "target_artifact")
