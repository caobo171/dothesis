"""widen paper_uploads.mime_type to hold long Office mime types

The original VARCHAR(64) fits application/pdf (15 chars) but overflows on the
DOCX mime type application/vnd.openxmlformats-officedocument.wordprocessingml.document
(71 chars), which now arrives via the partner-report / DOCX upload path and 500s
with StringDataRightTruncation. Widen to VARCHAR(255) (standard mime column size).

Revision ID: 20260715_paperupmime01
Revises: 20260708_coachnudge01
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa

revision = "20260715_paperupmime01"
down_revision = "20260708_coachnudge01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "paper_uploads", "mime_type",
        type_=sa.String(length=255),
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "paper_uploads", "mime_type",
        type_=sa.String(length=64),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
