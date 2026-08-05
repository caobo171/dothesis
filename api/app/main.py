import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import admin_announcements as admin_announcements_router
from .routers import admin_jobs as admin_jobs_router
from .routers import admin_orders as admin_orders_router
from .routers import admin_papers as admin_papers_router
from .routers import admin_users as admin_users_router
from .routers import announcements as announcements_router
from .routers import admin_connectors as admin_connectors_router
from .routers import admin_tools as admin_tools_router
from .routers import connectors as connectors_router
from .routers import auth as auth_router
from .routers import credit as credit_router
from .routers import jobs as jobs_router
from .routers import papers as papers_router
from .settings import get_settings, reset_settings

log = logging.getLogger(__name__)


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

    # Orchestrator startup priming. Chat turns run on the v3 deep agent, which
    # reuses the orchestrator's shared async Postgres pool (chat_v3's
    # checkpointer) — warm it so the first turn isn't slow. Auto-draft still
    # runs the engine's auto graph (sync PostgresSaver, subprocess-invoked).
    if settings.orchestrator_enabled:
        try:
            from orchestrator.graph import _get_async_pool, get_auto_graph
            await _get_async_pool()
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
    # A localhost WEB_ORIGIN behind a real deployment is silent-but-fatal: the
    # verify / reset-password links mailed out point at the user's own machine.
    # Nothing else fails, so it only surfaces when someone clicks the link.
    for name, value in (("WEB_ORIGIN", settings.web_origin),
                        ("DOTHESIS_BASE_URL", settings.dothesis_base_url)):
        if "localhost" in value or "127.0.0.1" in value:
            log.warning("%s is %s — emailed links and payment return URLs will "
                        "point at localhost. Set it to the public origin.", name, value)
    app = FastAPI(title="DoThesis API", version="0.1.0", lifespan=lifespan)
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
        # The document tools answer with a FILE, so their counts have nowhere to
        # ride but headers. A cross-origin response hides every header not named
        # here — allow_headers governs the REQUEST — so without this the web app
        # downloads a .docx and can say nothing about what changed in it.
        expose_headers=[
            "Content-Disposition",
            "X-Credits-Charged",
            "X-Paragraphs-Rewritten",
            "X-Paragraphs-Skipped",
            "X-Citations-Resolved",
            "X-Citations-Unresolved",
            "X-Citations-Weak",
            "X-References-Uncited",
            "X-Citations-Added",
            "X-Citations-Linked",
            "X-Claims-Marked",
            "X-References",
        ],
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
    # Connected AI apps (MCP connectors). Unconditional, not behind the
    # orchestrator flag: a user must be able to see and revoke a grant even
    # on a deploy where the tool surface itself is switched off.
    app.include_router(connectors_router.router, prefix="/api/v1")
    app.include_router(admin_connectors_router.router, prefix="/api/v1")
    app.include_router(admin_tools_router.router, prefix="/api/v1")

    # E2E test seams — mounted ONLY under DOTHESIS_TEST_SUPPORT=1 (defaults
    # off; see routers/test_support.py for the threat-model notes). Placed
    # before the orchestrator block on purpose: the auth/billing suite needs
    # these seams even in configs where chat (orchestrator) is off.
    if settings.test_support_enabled:
        from .routers import test_support as test_support_router
        app.include_router(test_support_router.router, prefix="/api/v1")

    if settings.orchestrator_enabled:
        from .routers import chat as chat_router
        from .routers import exports as exports_router  # SP6: M5 export download
        from .routers import m5_editor as m5_editor_router  # SP6.5: editor surface
        from .routers import partner_report as partner_report_router  # partner cross-product report
        from .routers import runs as runs_router
        from .routers import uploads as uploads_router
        from .routers import import_route as import_router  # F12: mid-journey state import
        from .routers import roadmap as roadmap_router  # F2: derived coaching roadmap
        from .routers import field_it as field_it_router  # F7: survey handoff + results ingestion
        from .routers import humanize as humanize_router  # MCP: humanize tool endpoint
        from .routers import skills as skills_router      # chat skill picker catalogue
        app.include_router(chat_router.router, prefix="/api/v1")
        app.include_router(exports_router.router, prefix="/api/v1")  # SP6
        app.include_router(m5_editor_router.router, prefix="/api/v1")  # SP6.5
        app.include_router(runs_router.router, prefix="/api/v1")
        app.include_router(uploads_router.router, prefix="/api/v1")
        app.include_router(partner_report_router.router, prefix="/api/v1")
        # F12: reuses uploads' S3 fetch + chat_v3 workspace, so it lives in the orchestrator block.
        app.include_router(import_router.router, prefix="/api/v1")
        # F2: chat-only coaching surface (uses chat_v3 workspace); orchestrator block.
        app.include_router(roadmap_router.router, prefix="/api/v1")
        # F7: Field-It survey handoff + results ingestion (uses chat_v3 workspace
        # + DbProjectStateStore); orchestrator block like the roadmap surface.
        app.include_router(field_it_router.router, prefix="/api/v1")
        app.include_router(humanize_router.router, prefix="/api/v1")  # MCP humanize
        # Stateless helper tools (writing rhythm, citation check). In the
        # orchestrator block because writing-rhythm imports the detector.
        from .routers import tools as tools_router  # noqa: PLC0415
        app.include_router(tools_router.router, prefix="/api/v1")
        # Skill catalogue for the chat picker. Orchestrator block because the
        # skills it lists are the ones the deep agent loads (agent/runtime.py).
        app.include_router(skills_router.router, prefix="/api/v1")

    # F4: wire the cross-project advisor-theme distill hook. The agent tool
    # mark_feedback_addressed calls agent.memory_hook.distill_advisor_themes once
    # every directive is addressed; the agent layer can't import app, so the real
    # impl is set here — resolving user_id from the store's project_id.
    import agent.memory_hook as _memory_hook

    def _distill(store, advisor_feedback) -> None:
        import logging
        pid = getattr(store, "project_id", None)
        if pid is None:
            return  # file-backed store (e.g. tests) — no user to distill to
        from .db import get_session_factory
        from .models import Project
        from .user_memory import distill_advisor_themes
        try:
            with get_session_factory()() as db:
                proj = db.get(Project, pid)
                if proj is not None:
                    distill_advisor_themes(db, proj.user_id, advisor_feedback,
                                           source_project_id=pid)
                    db.commit()
        except Exception:
            logging.getLogger(__name__).exception("distill hook failed")

    _memory_hook.distill_advisor_themes = _distill

    # F5: wire the agent-layer analytics hook. agent/ and quality/ call
    # agent.analytics.emit (a no-op by default) so they never import app; here the
    # app rebinds it to the real best-effort PostHog emitter. Same indirection as
    # the memory hook above.
    import agent.analytics as _agent_analytics
    from .analytics import emit as _emit
    _agent_analytics.emit = _emit

    return app


app = create_app()
