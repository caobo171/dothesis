"""shared cache for paid citation and web searches

Every draft fires ~40 research queries. Each one used to hit Crossref, OpenAlex,
Semantic Scholar AND a Google-grounded Gemini call, and the only memo of the
answers was a JSON file relative to whichever cwd the worker happened to have,
so nothing was shared between hosts, processes, or even two checkouts on one
machine. A 34-job test day paid for 1,140 grounded searches this way.

`search_cache` is the one memo every worker and host shares. `key` is the
sha256 of (kind, model, query); `payload` is the answer (its inner result is
null for a "searched, found nothing" entry so a miss is remembered too); rows
expire after 30 days for hits and 3 days for misses.

Revision ID: 20260907_searchcache01
Revises: 20260903_dropneedsreview01
Create Date: 2026-09-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260907_searchcache01"
down_revision = "20260903_dropneedsreview01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_cache_kind", "search_cache", ["kind"])
    op.create_index("ix_search_cache_expires_at", "search_cache", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_search_cache_expires_at", table_name="search_cache")
    op.drop_index("ix_search_cache_kind", table_name="search_cache")
    op.drop_table("search_cache")
