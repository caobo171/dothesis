"""blog posts and categories

DoThesis had no blog at all: no table, no route, no sitemap — the landing
footer linked "Blog" to `#`. These two tables are the storage half of the
content engine that fills that gap with a measured Vietnamese content bank on
quantitative thesis research.

`blog_posts.body` is markdown and there is no `body_format` column: this blog
is greenfield, so it never has to carry WELE's half-finished Quill-HTML to
markdown migration.

`status` is 0 draft / 1 published / 2 scheduled, and a post counts as visible
when it is published, or scheduled with `scheduled_at` in the past. That is why
the `(status, published_at)` index exists — every public listing filters on
exactly that pair. `(locale, slug)` is unique rather than `slug` alone because
the same article will exist per locale.

`focus_keyword` is nullable on purpose: the duplicate guard keys on it and
treats a null as "this post never blocks and is never blocked", which is the
only rule that survived calibration against a corpus of templated titles.

Revision ID: 20260908_blog01
Revises: 20260907_searchcache01
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_blog01"
down_revision = "20260907_searchcache01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blog_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("intro_md", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "blog_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("locale", sa.String(8), nullable=False, server_default="vi"),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("blog_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_title", sa.String(200), nullable=True),
        sa.Column("meta_description", sa.String(400), nullable=True),
        sa.Column("focus_keyword", sa.String(200), nullable=True),
        sa.Column("secondary_keywords", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("focus_keyword_volume", sa.Integer(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("duplicate_override_reason", sa.Text(), nullable=True),
        sa.Column("reading_time", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archetype", sa.String(40), nullable=True),
        sa.Column("source_batch", sa.String(64), nullable=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("locale", "slug", name="uq_blog_posts_locale_slug"),
    )
    # Named to match the model's __table_args__ / SQLAlchemy's naming so a
    # metadata-vs-migration diff stays empty.
    op.create_index("ix_blog_posts_status_published_at", "blog_posts",
                    ["status", "published_at"])
    op.create_index("ix_blog_posts_category_id", "blog_posts", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_blog_posts_category_id", table_name="blog_posts")
    op.drop_index("ix_blog_posts_status_published_at", table_name="blog_posts")
    op.drop_table("blog_posts")
    op.drop_table("blog_categories")
