"""widen exports.scope to hold a multi-module set

A single export can now cover several modules at once (the UI lets the user pick
multiple), stored as a comma-joined string like "M1,M3,M4" — too long for the
original VARCHAR(8). Widen to VARCHAR(64).

Revision ID: 20260630_expscope01
Revises: 20260630_exports01
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260630_expscope01"
down_revision = "20260630_exports01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "exports", "scope",
        type_=sa.String(length=64),
        existing_type=sa.String(length=8),
        existing_nullable=False,
        existing_server_default="full",
    )


def downgrade() -> None:
    op.alter_column(
        "exports", "scope",
        type_=sa.String(length=8),
        existing_type=sa.String(length=64),
        existing_nullable=False,
        existing_server_default="full",
    )
