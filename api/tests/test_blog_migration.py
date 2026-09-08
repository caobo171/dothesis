"""The blog migration is real: the whole chain applies, and it comes back off.

Why the whole chain and not just the one revision: `conftest._bind_db` builds
the schema with `Base.metadata.create_all`, so nothing in the suite would ever
notice a migration that disagrees with the models — or a broken `down_revision`
link. This test is the only place the migrations themselves run, so it starts
from an empty database and walks `base -> head`.
"""
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db import Base, get_engine
from app.settings import reset_settings

REVISION = "20260908_blog01"
# The revision that put a locale on blog_categories, and the one under it.
LOCALE_REVISION = "20260909_blogcatloc01"
BEFORE_BLOG = "20260907_searchcache01"


def _alembic_config() -> Config:
    """An alembic config with NO ini file, only a script location.

    Deliberately not `Config("alembic.ini")`: `migrations/env.py` calls
    `fileConfig(config.config_file_name)` when one is set, and that
    reconfigures Python's logging from scratch — `disable_existing_loggers`
    defaults to true, so every logger already created is switched off for the
    rest of the process. Three unrelated tests later in the suite assert on
    `caplog` records and started failing here, in a way that only appeared in a
    full run. With no file to read, env.py skips `fileConfig` and the
    migrations still get their URL from `config.set_main_option`.
    """
    from pathlib import Path

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    return cfg


@pytest.fixture
def empty_db(pg_url, monkeypatch):
    """A database with no tables at all, and env.py pointed at it."""
    monkeypatch.setenv("DATABASE_URL", pg_url)
    reset_settings()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    yield engine
    # Leave the database as the autouse fixture expects to find it.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset_settings()


def test_migration_chain_creates_blog_tables(empty_db):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    insp = inspect(empty_db)
    tables = set(insp.get_table_names())
    assert "blog_categories" in tables
    assert "blog_posts" in tables

    post_cols = {c["name"] for c in insp.get_columns("blog_posts")}
    # Every column §7 of the design names, so a silently dropped one fails here
    # rather than at insert time in the CLI.
    assert post_cols >= {
        "id", "locale", "slug", "title", "body", "excerpt", "image_url",
        "category_id", "tags", "status", "published_at", "scheduled_at",
        "meta_title", "meta_description", "focus_keyword", "secondary_keywords",
        "focus_keyword_volume", "canonical_url", "duplicate_override_reason",
        "reading_time", "archetype", "source_batch", "views",
        "created_at", "updated_at",
    }

    uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("blog_posts")}
    assert ("locale", "slug") in uniques, uniques

    indexes = {i["name"] for i in insp.get_indexes("blog_posts")}
    assert "ix_blog_posts_status_published_at" in indexes
    assert "ix_blog_posts_category_id" in indexes

    cat_cols = {c["name"] for c in insp.get_columns("blog_categories")}
    assert "locale" in cat_cols

    cat_uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("blog_categories")}
    # Same shape as blog_posts: one row per (locale, slug), so the Vietnamese
    # and English editions of a hub can share a slug and a URL segment.
    assert ("locale", "slug") in cat_uniques, cat_uniques
    assert ("slug",) not in cat_uniques, cat_uniques


def test_migration_downgrades(empty_db):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    # To the revision under the blog, not `-1`: the blog is two revisions now.
    command.downgrade(cfg, BEFORE_BLOG)

    tables = set(inspect(empty_db).get_table_names())
    assert "blog_posts" not in tables
    assert "blog_categories" not in tables


# --- the locale column, on a database that already has live categories -----

def _insert_category(engine, slug: str, *, locale: str | None = None) -> None:
    cols = "id, slug, name, display_name, sort_order"
    vals = "gen_random_uuid(), :slug, :slug, :slug, 0"
    params = {"slug": slug}
    if locale is not None:
        cols, vals = cols + ", locale", vals + ", :locale"
        params["locale"] = locale
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO blog_categories ({cols}) VALUES ({vals})"), params)


def test_existing_categories_are_backfilled_to_vi(empty_db):
    """The blog was live before this column existed, so the backfill is the point.

    Seven Vietnamese category rows and 420 posts were in production when this
    revision was written. A row that came out of it with a NULL or empty locale
    would vanish from the locale-filtered categories route and orphan every post
    pointing at it, so this asserts the pre-existing rows, not a fresh insert.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, REVISION)
    _insert_category(empty_db, "spss")
    _insert_category(empty_db, "smartpls")

    command.upgrade(cfg, LOCALE_REVISION)

    with empty_db.begin() as conn:
        rows = dict(conn.execute(text("SELECT slug, locale FROM blog_categories")).all())
    assert rows == {"spss": "vi", "smartpls": "vi"}


def test_the_same_slug_in_two_locales_is_allowed_after_the_migration(empty_db):
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    _insert_category(empty_db, "spss", locale="vi")
    _insert_category(empty_db, "spss", locale="en")

    with empty_db.begin() as conn:
        count = conn.scalar(text("SELECT count(*) FROM blog_categories WHERE slug = 'spss'"))
    assert count == 2


def test_the_locale_column_comes_back_off(empty_db):
    """Down one revision: the column goes, slug is unique again, en rows are gone.

    Deleting the non-`vi` rows is not incidental — two rows sharing a slug
    cannot coexist under the old constraint, so the downgrade has to choose, and
    it keeps the locale the blog launched with.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    _insert_category(empty_db, "spss", locale="vi")
    _insert_category(empty_db, "spss", locale="en")

    command.downgrade(cfg, REVISION)

    insp = inspect(empty_db)
    assert "locale" not in {c["name"] for c in insp.get_columns("blog_categories")}
    cat_uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("blog_categories")}
    assert ("slug",) in cat_uniques, cat_uniques
    with empty_db.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM blog_categories")) == 1
