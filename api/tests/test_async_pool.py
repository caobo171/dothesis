"""The async PG pool lives in app.db, not in the orchestrator graph module.

Regression guard for the auto-draft migration: chat_v3 builds its
AsyncPostgresSaver from this pool, so if the helper ever moves back behind
orchestrator.graph, deleting that module silently kills interactive chat.
"""
import inspect


def test_app_db_exposes_get_async_pool():
    from app import db
    assert inspect.iscoroutinefunction(db.get_async_pool)


def test_chat_v3_does_not_import_the_pool_from_orchestrator():
    from app.routers import chat_v3
    src = inspect.getsource(chat_v3)
    assert "orchestrator.graph" not in src


# No skipif here on purpose: every test under api/tests/ gets a real
# DATABASE_URL from conftest.py's autouse _bind_db fixture (backed by the
# session-scoped PostgresContainer), so a DB-availability guard is both
# unnecessary and actively wrong here — a `skipif` condition is evaluated at
# collection time, before _bind_db has run, so DATABASE_URL always reads
# unset and the test would always skip. Don't re-add one.
async def test_pool_is_memoized():
    """One pool per process: a second call must hand back the same object, not
    open a second connection pool against the same database."""
    from app import db
    try:
        assert await db.get_async_pool() is await db.get_async_pool()
    finally:
        # get_async_pool()'s AsyncConnectionPool spawns a non-daemon worker
        # thread once opened (confirmed by sampling a hung run: the thread
        # sits parked on its internal work queue). In the API process that's
        # fine — the pool is meant to outlive the process. In pytest nothing
        # else ever closes it, so left open it blocks interpreter shutdown
        # forever: every assertion in this file passes and the process still
        # never exits. Close it and clear the module global so this test
        # doesn't leak a hung process into the run, and so a later test in
        # the same session gets a fresh pool instead of a closed one.
        if db._async_pool is not None:
            await db._async_pool.close()
            db._async_pool = None
