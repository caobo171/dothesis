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
    from app.db import Base, get_engine, reset_engine_for_tests
    reset_engine_for_tests(pg_url)
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    yield
    # Teardown: drop all tables so migration tests start from a clean DB
    # (SQLAlchemy-created tables have no alembic_version row, which confuses
    # Alembic's downgrade/upgrade cycle if tables are left behind).
    Base.metadata.drop_all(get_engine())
