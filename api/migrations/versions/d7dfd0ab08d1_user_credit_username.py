"""user_credit_username

Revision ID: d7dfd0ab08d1
Revises: a1c2d3e4f501
Create Date: 2026-05-23 20:05:29.780664

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7dfd0ab08d1"
down_revision: Union[str, None] = "a1c2d3e4f501"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("username", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("credit", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "credit")
    op.drop_column("users", "username")
