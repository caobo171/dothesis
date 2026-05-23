import pytest
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

from app.db import Base, get_engine, reset_engine_for_tests


@pytest.fixture(scope="session")
def pg_url():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg.get_connection_url().replace("psycopg2", "psycopg")


@pytest.fixture(autouse=True)
def _bind_db(pg_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    reset_engine_for_tests(pg_url)
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    yield
