"""The async PG pool lives in app.db, not in the orchestrator graph module.

Regression guard for the auto-draft migration: chat_v3 builds its
AsyncPostgresSaver from this pool, so if the helper ever moves back behind
orchestrator.graph, deleting that module silently kills interactive chat.
"""
import inspect
import os

import pytest


def test_app_db_exposes_get_async_pool():
    from app import db
    assert inspect.iscoroutinefunction(db.get_async_pool)


def test_chat_v3_does_not_import_the_pool_from_orchestrator():
    from app.routers import chat_v3
    src = inspect.getsource(chat_v3)
    assert "orchestrator.graph" not in src


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database URL")
async def test_pool_is_memoized():
    """One pool per process: a second call must hand back the same object, not
    open a second connection pool against the same database."""
    from app import db
    assert await db.get_async_pool() is await db.get_async_pool()
