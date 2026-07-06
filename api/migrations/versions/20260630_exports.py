"""create exports table (module-agnostic export documents)

Exports used to live in `context_store.m5_writing.export_artifacts`, which made a
per-module export show up under M5 Writing. They're now first-class rows tagged
with `scope` ("full" or "M1".."M4"). Backfills existing artifacts as scope=full.

Revision ID: 20260630_exports01
Revises: 20260625_usermem01
Create Date: 2026-06-30
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260630_exports01"
down_revision = "20260625_usermem01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(length=8), server_default="full", nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exports_project_id", "exports", ["project_id"])

    # Backfill: lift existing m5_writing.export_artifacts into rows (scope=full).
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT project_id, m5_writing FROM context_store WHERE m5_writing IS NOT NULL")
    ).fetchall()
    ins = sa.text(
        "INSERT INTO exports (id, project_id, scope, kind, s3_key, filename, size_bytes, created_at) "
        "VALUES (:id, :pid, 'full', :kind, :s3_key, :filename, :size, now())"
    )
    for project_id, m5 in rows:
        artifacts = (m5 or {}).get("export_artifacts") or []
        for a in artifacts:
            s3_key = a.get("s3_key")
            if not s3_key:
                continue
            conn.execute(ins, {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "kind": a.get("kind") or "docx",
                "s3_key": s3_key,
                "filename": s3_key.rsplit("/", 1)[-1],
                "size": int(a.get("size_bytes") or 0),
            })


def downgrade() -> None:
    op.drop_index("ix_exports_project_id", table_name="exports")
    op.drop_table("exports")
