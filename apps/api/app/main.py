"""FastAPI application factory."""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

import structlog

from app.core.logging import configure_logging, get_logger
from app.core.settings import get_settings
from app.db.session import Base, engine

# Import all models so metadata knows about them
import app.domains.workspaces.models  # noqa: F401
import app.domains.workload.models  # noqa: F401
import app.domains.plans.models  # noqa: F401
import app.domains.indexes.models  # noqa: F401
import app.domains.experiments.models  # noqa: F401

from app.api.workspaces import router as workspaces_router
from app.api.workload import router as workload_router
from app.api.queries import router as queries_router
from app.api.experiments import router as experiments_router
from app.api.recommendations import router as recommendations_router
from app.api.indexes import router as indexes_router
from app.api.jobs import router as jobs_router

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on startup when DB is reachable
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("db_schema_initialized")
    except Exception as exc:
        logger.warning("db_schema_init_deferred", error=str(exc))
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="PlanGuard API",
        description="PostgreSQL Workload Analyzer & Index Experimentation",
        version=settings.app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID + structured logging middleware
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next: object) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response: Response = await call_next(request)  # type: ignore[arg-type]
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    # Health check
    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "version": settings.app_version}

    # Register all API v1 domain routers
    app.include_router(workspaces_router, prefix="/api/v1")
    app.include_router(workload_router, prefix="/api/v1")
    app.include_router(queries_router, prefix="/api/v1")
    app.include_router(experiments_router, prefix="/api/v1")
    app.include_router(recommendations_router, prefix="/api/v1")
    app.include_router(indexes_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")

    return app


app = create_app()
