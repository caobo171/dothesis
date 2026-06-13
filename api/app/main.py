from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import admin_announcements as admin_announcements_router
from .routers import admin_jobs as admin_jobs_router
from .routers import admin_orders as admin_orders_router
from .routers import admin_papers as admin_papers_router
from .routers import admin_users as admin_users_router
from .routers import announcements as announcements_router
from .routers import auth as auth_router
from .routers import credit as credit_router
from .routers import jobs as jobs_router
from .routers import papers as papers_router
from .settings import get_settings, reset_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.job_workdir_root.mkdir(parents=True, exist_ok=True)

    # Capture the running event loop so job_runner.start_monitor can schedule
    # the events-tailing task even when called from a SYNC endpoint (which
    # FastAPI runs in a threadpool worker with no running loop — that was the
    # "no running event loop" 500 when starting an auto-approve run).
    import asyncio as _asyncio

    from . import job_runner
    job_runner.set_app_loop(_asyncio.get_running_loop())

    # Orchestrator: prime the graph cache at startup so first chat turn isn't slow.
    # Interactive needs AsyncPostgresSaver (chat uses graph.astream); auto-mode
    # stays on sync PostgresSaver (subprocess invokes synchronously).
    if settings.orchestrator_enabled:
        try:
            from orchestrator.graph import get_auto_graph, init_interactive_graph
            await init_interactive_graph()
            get_auto_graph()
        except Exception:
            import logging
            logging.exception("orchestrator graph init failed (continuing without it)")

        # Brief §1.8 — register the SQL sink for the token meter so every
        # metered_invoke call gets persisted to token_ledger. Wired in
        # lifespan (not at import) because the meter only matters when the
        # orchestrator is enabled; eval-only processes don't need it.
        try:
            _register_token_meter_sink()
        except Exception:
            import logging
            logging.exception("token meter sink registration failed")

    yield


def _register_token_meter_sink() -> None:
    """Hook the orchestrator's token meter to the api DB session.

    The sink runs in the LLM-invoke thread (bounded_invoke uses a
    ThreadPoolExecutor), so we open a fresh short-lived session per
    write rather than sharing one with the request handler — cleaner
    lifetime and avoids leaking a thread-local Session reference.
    """
    from orchestrator.token_meter import LedgerEntry, register_sink
    from .db import get_session_factory
    from .models import TokenLedger

    def _sink(entry: LedgerEntry) -> None:
        sf = get_session_factory()
        with sf() as db:
            db.add(TokenLedger(
                project_id=entry.project_id,
                action_kind=entry.action_kind,
                model=entry.model,
                prompt_tokens=entry.prompt_tokens,
                completion_tokens=entry.completion_tokens,
                reserved=entry.reserved,
                duration_ms=entry.duration_ms,
            ))
            db.commit()

    register_sink(_sink)


def create_app() -> FastAPI:
    # Reset cached settings so that env-var monkeypatching in tests takes effect.
    reset_settings()
    settings = get_settings()
    app = FastAPI(title="OpenDraft API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        # allow_credentials is False because we no longer use cookies for
        # auth — the access_token rides in the request JSON body (see
        # jwt_auth.py and CLAUDE.md). Setting it True would still work but
        # signal intent inaccurately, since no fetch on the client uses
        # `credentials: "include"` anymore.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    def health():
        return {"ok": True}

    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(papers_router.router, prefix="/api/v1")
    app.include_router(jobs_router.router, prefix="/api/v1")
    app.include_router(credit_router.router, prefix="/api/v1")
    app.include_router(admin_users_router.router, prefix="/api/v1")
    app.include_router(admin_papers_router.router, prefix="/api/v1")
    app.include_router(admin_jobs_router.router, prefix="/api/v1")
    app.include_router(admin_orders_router.router, prefix="/api/v1")
    app.include_router(admin_announcements_router.router, prefix="/api/v1")
    app.include_router(announcements_router.router, prefix="/api/v1")

    if settings.orchestrator_enabled:
        from .routers import chat as chat_router
        from .routers import exports as exports_router  # SP6: M5 export download
        from .routers import m5_editor as m5_editor_router  # SP6.5: editor surface
        from .routers import runs as runs_router
        from .routers import uploads as uploads_router
        app.include_router(chat_router.router, prefix="/api/v1")
        app.include_router(exports_router.router, prefix="/api/v1")  # SP6
        app.include_router(m5_editor_router.router, prefix="/api/v1")  # SP6.5
        app.include_router(runs_router.router, prefix="/api/v1")
        app.include_router(uploads_router.router, prefix="/api/v1")

    return app


app = create_app()
