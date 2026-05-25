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
