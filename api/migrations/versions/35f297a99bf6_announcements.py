"""announcements

Revision ID: 35f297a99bf6
Revises: ffe6dccd65df
Create Date: 2026-05-24 05:09:54.205313

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '35f297a99bf6'
down_revision: Union[str, Sequence[str], None] = 'ffe6dccd65df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("image_url", sa.Text),
        sa.Column("cta_label", sa.String(64)),
        sa.Column("cta_url", sa.Text),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_announcements_kind_active", "announcements", ["kind", "active"])


def downgrade() -> None:
    op.drop_index("ix_announcements_kind_active", table_name="announcements")
    op.drop_table("announcements")
