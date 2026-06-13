"""add messages.cost_credits + messages.duration_ms

Per-response cost + latency, shown in the chat message footer and summed for
the thread (right panel) and project (left panel) totals. Nullable-with-default
so existing rows and any code path that doesn't set them stays valid.

Revision ID: 20260613_msgcost01
Revises: 20260603_vhist01
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa

revision = "20260613_msgcost01"
down_revision = "20260603_vhist01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("cost_credits", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "messages",
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "messages",
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("messages", "total_tokens")
    op.drop_column("messages", "duration_ms")
    op.drop_column("messages", "cost_credits")
