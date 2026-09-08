"""blog categories become per-locale

`blog_categories` was created unique on `slug` alone, with one Vietnamese
`name`, `display_name` and `intro_md` per row. That was right while the bank
was Vietnamese only. It is wrong the moment an English edition exists: the
category copy IS the category page's content, so `/blog/en/chu-de/spss` would
have rendered a Vietnamese heading and a Vietnamese 350-word intro.

So: a `locale` column, and the uniqueness moves from `slug` to
`(locale, slug)` — the same shape `blog_posts` has already. The slug stays the
same across locales on purpose, so the two language editions of a hub share a
URL segment and a reader switching language lands on the matching page.

The backfill is not optional. This column arrives AFTER the blog went live:
there are 420 published Vietnamese posts and seven category rows in production
that predate it. Those rows are all Vietnamese, and a NULL or empty locale on
any of them would drop the category out of `POST /blog/categories` (which now
filters on locale) and orphan every post that points at it. Hence the explicit
UPDATE below rather than a bare NOT NULL column with a default that only a
fresh insert would ever see.

`downgrade()` has to delete any non-`vi` category, because without the locale
column two rows sharing a slug cannot both exist. Posts pointing at a deleted
category fall back to NULL through the existing ON DELETE SET NULL. That is
the honest cost of reversing this, and it is why the downgrade is destructive
in one direction only: nothing Vietnamese is touched.

Revision ID: 20260909_blogcatloc01
Revises: 20260908_blog01
Create Date: 2026-09-09
"""
import sqlalchemy as sa
from alembic import op

revision = "20260909_blogcatloc01"
down_revision = "20260908_blog01"
branch_labels = None
depends_on = None

TABLE = "blog_categories"
NEW_UNIQUE = "uq_blog_categories_locale_slug"
# What Postgres named the constraint that `sa.Column(..., unique=True)` created
# in 20260908_blog01. Only used to restore it on the way back down; on the way
# up the real name is reflected, because an implicitly-created constraint's
# name is Postgres's choice and not one this repo ever wrote down.
OLD_UNIQUE = "blog_categories_slug_key"


def _slug_only_unique_constraints(bind) -> list[str]:
    """Names of the unique constraints on exactly `(slug)`."""
    return [c["name"] for c in sa.inspect(bind).get_unique_constraints(TABLE)
            if list(c["column_names"]) == ["slug"] and c.get("name")]


def upgrade() -> None:
    bind = op.get_bind()

    # Nullable first, then filled, then locked down: the rows that exist right
    # now are live production content, and they have to come out of this
    # migration with a real locale on them, not a default nobody applied.
    op.add_column(TABLE, sa.Column("locale", sa.String(8), nullable=True))
    op.execute(f"UPDATE {TABLE} SET locale = 'vi' WHERE locale IS NULL")
    op.alter_column(TABLE, "locale", nullable=False, server_default="vi")

    for name in _slug_only_unique_constraints(bind):
        op.drop_constraint(name, TABLE, type_="unique")
    op.create_unique_constraint(NEW_UNIQUE, TABLE, ["locale", "slug"])


def downgrade() -> None:
    op.drop_constraint(NEW_UNIQUE, TABLE, type_="unique")
    # Anything not Vietnamese cannot survive a unique index on slug alone, and
    # its copy is untranslatable back into the single-locale schema. Delete it;
    # blog_posts.category_id is ON DELETE SET NULL, so the posts survive.
    op.execute(f"DELETE FROM {TABLE} WHERE locale <> 'vi'")
    op.drop_column(TABLE, "locale")
    op.create_unique_constraint(OLD_UNIQUE, TABLE, ["slug"])
