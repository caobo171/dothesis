"""add message context occupancy and automatic compaction threshold

Revision ID: 20260912_msgctx01
Revises: 20260912_toolrunproj01
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_msgctx01"
down_revision = "20260912_toolrunproj01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("context_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "messages",
        sa.Column("compact_at_tokens", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("messages", "compact_at_tokens")
    op.drop_column("messages", "context_tokens")
