import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, future=True, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionLocal


def reset_engine_for_tests(url: str) -> None:
    """Test-only: rebind to a different DB URL."""
    global _engine, _SessionLocal
    _engine = create_engine(url, future=True, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def db_session() -> Generator[Session, None, None]:
    sess = get_session_factory()()
    try:
        yield sess
    finally:
        sess.close()


_async_pool = None


async def get_async_pool():
    """Lazy AsyncConnectionPool used by AsyncPostgresSaver.

    Moved here from orchestrator/graph.py during the Auto Thesis migration:
    routers/chat_v3.py's checkpointer needs this pool, and it must not die
    with the orchestrator graph layer (orchestrator is an editable-installed
    library and must not be a dependency of the API's own plumbing).

    Decision (carried over from the original): the chat router calls
    graph.astream(), which dispatches to the checkpointer's aget_tuple —
    only AsyncPostgresSaver implements that. The sync PostgresSaver raises
    NotImplementedError on the async path.
    """
    global _async_pool
    if _async_pool is None:
        from psycopg_pool import AsyncConnectionPool

        url = os.environ["DATABASE_URL"]
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        _async_pool = AsyncConnectionPool(
            url,
            min_size=1,
            max_size=int(os.getenv("ORCHESTRATOR_PG_POOL_MAX", "10")),
            kwargs={"autocommit": True},
            # Validate a connection before handing it out. DATABASE_URL points at
            # a REMOTE Postgres in dev, and an idle pooled connection over a WAN
            # gets reaped by NAT/firewall timeouts without either end noticing —
            # the pool then hands out a corpse and the caller dies mid-query with
            # "server closed the connection unexpectedly" (a 500 on send-message,
            # not a retry). check_connection turns that into a discard-and-replace
            # inside the pool. Costs one round-trip per checkout, which is noise
            # next to the LLM call it precedes.
            check=AsyncConnectionPool.check_connection,
            # psycopg_pool 3.2+ refuses to auto-open in async contexts to avoid
            # hidden blocking I/O during import — open() must be awaited explicitly.
            open=False,
        )
        await _async_pool.open()
    return _async_pool
