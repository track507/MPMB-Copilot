"""FastAPI application entry point"""

import asyncio
import secrets
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_keys as api_keys_api
from app.api import (
    auth as auth_api,
)
from app.api import chat, health, index, sessions, settings, tasks
from app.api import (
    source_catalog as source_catalog_api,
)
from app.api import uploads as uploads_api
from app.api.deps import current_principal, is_loopback, principal_or_service
from app.config import config
from app.logger import RequestLoggingMiddleware, configure_logging, get_logger
from app.services import get_vector_store, task_manager
from app.services.db import auth_service, db
from app.services.uploads import upload_service

# Initialize structured logging before anything else
configure_logging()
logger = get_logger(__name__)


async def _init_setup_token() -> str | None:
    """Fail-safe exposure: an exposed fresh install requires a one-time token to claim admin."""
    if is_loopback(config.bind_host):
        return None
    if await auth_service.count_users() > 0:
        return None
    token = secrets.token_urlsafe(16)
    # ! Printed once; required by POST /api/auth/setup while no admin exists
    logger.warning("setup_token_required", token=token, hint="submit as setup_token on the first-run setup screen")
    return token


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events"""
    # Startup
    logger.info(
        "app_starting",
        app=config.app_name,
        version=app.version,
        environment=config.environment,
        llm_provider=config.default_llm_provider,
        model=config.default_model,
        vector_store=config.vector_store,
        qdrant=f"{config.qdrant_host}:{config.qdrant_port}",
    )

    app.state.setup_token = None

    # Connect to PostgreSQL
    try:
        await db.connect(config.resolved_database_url, echo=config.is_development)
        if await db.health_check():
            logger.info("postgres_connected")
            from app.services.db.migrations import run_migrations

            await asyncio.to_thread(run_migrations)
            app.state.setup_token = await _init_setup_token()
        else:
            await db.disconnect()
            logger.warning("postgres_unavailable", error="Initial database health check failed")
    except Exception as e:
        logger.warning("postgres_unavailable", error=str(e))

    # Connect to the upload service
    await asyncio.to_thread(upload_service.sweep_stale_temps)

    # Connect to Qdrant
    store = get_vector_store()
    store_connected = await store.connect()
    if not store_connected:
        logger.warning("qdrant_unavailable")
    else:
        collection_info = await store.collection_info()
        logger.info("qdrant_connected", collection_info=collection_info)

    from app.services.source_catalog import source_catalog_service

    catalog_health = source_catalog_service.load()
    logger.info(
        "source_catalog_loaded_at_startup",
        state=catalog_health.state.value,
        symbol_count=catalog_health.symbol_count,
        object_count=catalog_health.object_count,
        catalog_path=catalog_health.catalog_path,
    )
    # Warm the model catalog cache so the first settings visit is a cache hit, not two provider round trips
    from app.core.model_catalog import get_model_catalog

    def _warmup_done(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            logger.warning("model_catalog_warmup_failed", error=str(task.exception()))

    app.state.catalog_warmup = asyncio.create_task(get_model_catalog())
    app.state.catalog_warmup.add_done_callback(_warmup_done)
    yield

    # Shutdown
    logger.info("app_shutting_down", app=config.app_name)
    await db.disconnect()
    await task_manager.shutdown()


# Create FastAPI application
app = FastAPI(
    title=config.app_name,
    description="RAG-powered assistant for MPMB character sheet development using Adobe Acrobat JavaScript (ES5)",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=f"{config.api_prefix}/docs",
    redoc_url=f"{config.api_prefix}/redoc",
    openapi_url=f"{config.api_prefix}/openapi.json",
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Handle uncaught exceptions"""
    logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if config.is_development else "An unexpected error occurred",
            "type": type(exc).__name__,
        },
    )


_wall = [Depends(current_principal)]
_ops_wall = [Depends(principal_or_service)]

app.include_router(health.router, prefix=config.api_prefix, tags=["Health"])
app.include_router(auth_api.router, prefix=config.api_prefix, tags=["Auth"])
app.include_router(chat.router, prefix=config.api_prefix, tags=["Chat"], dependencies=_wall)
app.include_router(index.router, prefix=config.api_prefix, tags=["Indexing"], dependencies=_ops_wall)
app.include_router(sessions.router, prefix=config.api_prefix, tags=["Sessions"], dependencies=_wall)
app.include_router(tasks.router, prefix=config.api_prefix, tags=["Tasks"], dependencies=_ops_wall)
app.include_router(settings.router, prefix=config.api_prefix, tags=["Settings"], dependencies=_wall)
app.include_router(api_keys_api.router, prefix=config.api_prefix, tags=["API Keys"])
app.include_router(source_catalog_api.router, prefix=config.api_prefix, tags=["Source Catalog"], dependencies=_wall)
app.include_router(uploads_api.router, prefix=config.api_prefix, tags=["Uploads"], dependencies=_wall)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - redirect to docs"""
    return {
        "name": config.app_name,
        "version": "0.2.0",
        "status": "running",
        "docs": f"{config.api_prefix}/docs",
        "health": f"{config.api_prefix}/health",
    }


if __name__ == "__main__":
    import uvicorn

    # ! Bind the configured host, not a hardcoded 0.0.0.0: the exposure fail-safe keys off config.bind_host, so the launcher and the fail-safe must never disagree about whether we are exposed
    uvicorn.run(
        "app.main:app",
        host=config.bind_host,
        port=8000,
        reload=config.is_development,
        log_level=config.log_level.lower(),
    )
