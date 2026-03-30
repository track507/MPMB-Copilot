"""FastAPI application entry point"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, health, index, tasks
from app.config import config
from app.services import get_vector_store, task_manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting {config.app_name} v{app.version}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"LLM Provider: {config.default_llm_provider}")
    logger.info(f"Default Model: {config.default_model}")
    logger.info(f"Vector Store: {config.vector_store}")
    logger.info(f"Qdrant: {config.qdrant_host}:{config.qdrant_port}")

    store = get_vector_store()
    store_connected = await store.connect()
    if not store_connected:
        logger.warning("Failed to connect to Qdrant - vector search will not work")
    else:
        # Show collection info
        collection_info = await store.collection_info()
        logger.info(f"Qdrant collection info: {collection_info}")
    # TODO: Load embedding model
    # TODO: Verify MPMB source files exist

    yield

    # Shutdown
    logger.info(f"Shutting down {config.app_name}")
    await task_manager.shutdown()


# Create FastAPI application
app = FastAPI(
    title=config.app_name,
    description="RAG-powered assistant for MPMB character sheet development using Adobe Acrobat JavaScript (ES5)",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=f"{config.api_prefix}/docs",
    redoc_url=f"{config.api_prefix}/redoc",
    openapi_url=f"{config.api_prefix}/openapi.json",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Handle uncaught exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
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
app.include_router(tasks.router, prefix=config.api_prefix, tags=["Tasks"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint - redirect to docs"""
    return {
        "name": config.app_name,
        "version": "0.1.0",
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
