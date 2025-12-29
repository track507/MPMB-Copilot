"""FastAPI application entry point"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.api import health, chat, index

# Configure logging
logging.basicConfig(
	level=getattr(logging, settings.log_level),
	format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
	datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
	"""Application lifespan events"""
	# Startup
	logger.info(f"Starting {settings.app_name} v{app.version}")
	logger.info(f"Environment: {settings.environment}")
	logger.info(f"LLM Provider: {settings.default_llm_provider}")
	logger.info(f"Default Model: {settings.default_model}")
	logger.info(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")

	# TODO: Initialize Qdrant connection
	# TODO: Load embedding model
	# TODO: Verify MPMB source files exist

	yield

	# Shutdown
	logger.info(f"Shutting down {settings.app_name}")
	# TODO: Cleanup resources

# Create FastAPI application
app = FastAPI(
	title=settings.app_name,
	description="RAG-powered assistant for MPMB character sheet development using Adobe Acrobat JavaScript (ES5)",
	version="0.1.0",
	lifespan=lifespan,
	docs_url=f"{settings.api_prefix}/docs",
	redoc_url=f"{settings.api_prefix}/redoc",
	openapi_url=f"{settings.api_prefix}/openapi.json",
)

# CORS Middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.allowed_origins,
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
			"message": str(exc) if settings.is_development else "An unexpected error occurred",
			"type": type(exc).__name__,
		},
	)

# Include API routers
app.include_router(health.router, prefix=settings.api_prefix, tags=["Health"])
app.include_router(chat.router, prefix=settings.api_prefix, tags=["Chat"])
app.include_router(index.router, prefix=settings.api_prefix, tags=["Indexing"])

# Root endpoint
@app.get("/")
async def root():
	"""Root endpoint - redirect to docs"""
	return {
		"name": settings.app_name,
		"version": "0.1.0",
		"status": "running",
		"docs": f"{settings.api_prefix}/docs",
		"health": f"{settings.api_prefix}/health",
	}

if __name__ == "__main__":
	import uvicorn

	uvicorn.run(
		"app.main:app",
		host="0.0.0.0",
		port=8000,
		reload=settings.is_development,
		log_level=settings.log_level.lower(),
	)
