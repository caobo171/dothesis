"""Shared pytest fixtures for orchestrator tests.

Reuses the testcontainers Postgres fixture pattern from api/tests/conftest.py.
"""
import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


@pytest.fixture
def fake_llm_responses():
    return ["test response"]


@pytest.fixture(autouse=True)
def _bind_db(request, pg_url, monkeypatch):
    """Set DATABASE_URL and rebuild tables before each test (mirrors api/tests pattern).

    Tests that use the `alembic_env` fixture manage schema lifecycle via Alembic
    CLI (downgrade base → upgrade head). We skip both drop_all and create_all for
    those tests so the DB is left in whatever state the previous step produced,
    and each migration test's own `downgrade base` call provides the clean reset.

    For SQLAlchemy tests we drop_all both before AND after so the shared postgres
    container is left empty — this prevents SQLAlchemy-created tables (which lack
    an alembic_version row) from confusing Alembic-based migration tests that
    run later in the same session.
    """
    if "alembic_env" in request.fixturenames:
        yield
        return
    monkeypatch.setenv("DATABASE_URL", pg_url)
    # Lazy import — only matters for tests that exercise app.db.
    from sqlalchemy import text
    from app.db import Base, get_engine, reset_engine_for_tests
    reset_engine_for_tests(pg_url)
    # Nuke and recreate the schema, not just drop_all: the shared container can
    # carry a stale `projects` (e.g. from an Alembic migration test, or a schema
    # predating a later column like `last_nudge_at`). `create_all` skips tables
    # that already exist, so a stale table never gains new columns → ORM inserts
    # fail on the missing column. DROP SCHEMA CASCADE guarantees a clean rebuild
    # from the CURRENT models. (Migration tests take the alembic_env branch above
    # and never reach here.)
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(get_engine())
    yield
    # Teardown: leave a clean DB so a later Alembic migration test isn't confused
    # by SQLAlchemy-created tables (which lack an alembic_version row).
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
