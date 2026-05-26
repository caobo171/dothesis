"""add paper_uploads table

Revision ID: 20260527_uploads01
Revises: 20260526_orch01
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260527_uploads01"
down_revision = "20260526_orch01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_uploads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("s3_uri", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("text_extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_extract_uri", sa.Text, nullable=True),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_uploads")
