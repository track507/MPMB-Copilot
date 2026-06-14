"""FastAPI application entry point"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, health, index, sessions, settings, tasks
from app.api import source_catalog as source_catalog_api
from app.config import config
from app.logger import RequestLoggingMiddleware, configure_logging, get_logger
from app.services import get_vector_store, task_manager
from app.services.db import db

# Initialize structured logging before anything else
configure_logging()
logger = get_logger(__name__)


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

    # Connect to PostgreSQL
    try:
        await db.connect(config.resolved_database_url, echo=config.is_development)
        if await db.health_check():
            logger.info("postgres_connected")
        else:
            await db.disconnect()
            logger.warning("postgres_unavailable", error="Initial database health check failed")
    except Exception as e:
        logger.warning("postgres_unavailable", error=str(e))

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


# Include API routers
app.include_router(health.router, prefix=config.api_prefix, tags=["Health"])
app.include_router(chat.router, prefix=config.api_prefix, tags=["Chat"])
app.include_router(index.router, prefix=config.api_prefix, tags=["Indexing"])
app.include_router(sessions.router, prefix=config.api_prefix, tags=["Sessions"])
app.include_router(tasks.router, prefix=config.api_prefix, tags=["Tasks"])
app.include_router(settings.router, prefix=config.api_prefix, tags=["Settings"])
app.include_router(source_catalog_api.router, prefix=config.api_prefix, tags=["Source Catalog"])


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

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.is_development,
        log_level=config.log_level.lower(),
    )
