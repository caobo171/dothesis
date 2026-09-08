"""Pair a blog post with its translations.

The Vietnamese edition went live before an English one was planned, so the
column arrives on a table that already holds 839 rows. Those rows are the
originals: their key is their own slug, which is what the backfill writes, so
that every translation produced later can point at it and the two editions can
declare hreflang to each other.

Nullable rather than not-null: a post written in one language and never
translated has no pair, and inventing a key for it would say otherwise.

Revision ID: 20260909_blogtrkey01
Revises: 20260909_blogcatloc01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260909_blogtrkey01"
down_revision = "20260909_blogcatloc01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("blog_posts", sa.Column("translation_key", sa.String(200), nullable=True))
    op.create_index("ix_blog_posts_translation_key", "blog_posts", ["translation_key"])
    # Every row that exists when this runs is an original, so it is its own key.
    op.execute("UPDATE blog_posts SET translation_key = slug WHERE translation_key IS NULL")


def downgrade() -> None:
    op.drop_index("ix_blog_posts_translation_key", table_name="blog_posts")
    op.drop_column("blog_posts", "translation_key")
