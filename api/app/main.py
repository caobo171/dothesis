from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth as auth_router
from .routers import jobs as jobs_router
from .routers import papers as papers_router
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.job_workdir_root.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
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
    return app


app = create_app()
