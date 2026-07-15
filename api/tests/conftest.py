import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

from app.db import Base, get_engine, reset_engine_for_tests
from app.models import Project, User


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


def make_user(db: Session, **overrides) -> User:
    """Add a User with every NOT NULL column filled in, and flush it.

    Single source of truth for test users. `username` became unique + NOT NULL
    in af97307 and four hand-rolled fixtures broke at once because each built
    User() itself. When User gains the next required column, fill it in here so
    exactly one place has to change instead of every call site.
    """
    fields = {
        "email": f"t-{uuid.uuid4().hex[:8]}@x.com",
        "username": uuid.uuid4().hex[:8],
        "password_hash": "x",
        "email_verified": True,
    }
    fields.update(overrides)
    u = User(**fields)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def project_id():
    # Shared across test_agent_state.py and test_agent_state_coaching.py —
    # both need a real project row to hang a DbProjectStateStore off of.
    engine = get_engine()
    with Session(engine) as s:
        u = make_user(s)
        p = Project(user_id=u.id, name="T", current_module="M1", status="draft")
        s.add(p); s.commit()
        return p.id
