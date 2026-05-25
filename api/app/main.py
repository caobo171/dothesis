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
    yield


def create_app() -> FastAPI:
    # Reset cached settings so that env-var monkeypatching in tests takes effect.
    reset_settings()
    settings = get_settings()
    app = FastAPI(title="OpenDraft API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
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
        from .routers import runs as runs_router
        app.include_router(chat_router.router, prefix="/api/v1")
        app.include_router(runs_router.router, prefix="/api/v1")

    return app


app = create_app()
