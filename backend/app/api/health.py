"""Health check endpoint"""

from datetime import datetime, timezone

from fastapi import APIRouter, status

from app.config import config
from app.logger import get_logger
from app.model.schemas.health import HealthResponse, ServiceStatus, SourceCatalogHealthBlock
from app.model.schemas.source_catalog import CatalogState
from app.services.db import db
from app.services.source_catalog import source_catalog_service
from app.services.vector import get_vector_store

logger = get_logger(__name__)
router = APIRouter()


async def check_qdrant() -> ServiceStatus:
    """Check Qdrant connection"""
    try:
        store = get_vector_store()
        if not await store.health_check() and not await store.connect():
            return ServiceStatus(status="unavailable", message="Cannot connect to Qdrant")

        collection_info = await store.collection_info()
        if "error" in collection_info:
            return ServiceStatus(status="unavailable", message=collection_info["error"])

        vectors_count = collection_info.get("points_count", 0)
        return ServiceStatus(
            status="healthy", message=f"{config.qdrant_host}:{config.qdrant_port} ({vectors_count} vectors)"
        )
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return ServiceStatus(status="unavailable", message=str(e))


async def check_llm_provider() -> ServiceStatus:
    """Check LLM provider configuration"""
    try:
        api_key = config.get_llm_api_key()
        if config.default_llm_provider == "ollama":
            return ServiceStatus(status="configured", message=f"Ollama at {config.ollama_host}")
        elif api_key:
            return ServiceStatus(
                status="configured",
                message=f"{config.default_llm_provider} - {config.default_model}",
            )
        else:
            return ServiceStatus(
                status="not_configured",
                message=f"Missing API key for {config.default_llm_provider}",
            )
    except Exception as e:
        logger.error(f"LLM provider check failed: {e}")
        return ServiceStatus(status="error", message=str(e))


async def check_embedding_model() -> ServiceStatus:
    """Check embedding model availability"""
    try:
        # TODO: Actually load and test the model
        return ServiceStatus(
            status="ready",
            message=f"{config.embedding_provider}/{config.embedding_model}",
        )
    except Exception as e:
        logger.error(f"Embedding model check failed: {e}")
        return ServiceStatus(status="unavailable", message=str(e))


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Check the health status of the API and its dependencies",
)
async def health_check():
    """Health check endpoint that verifies all services"""
    logger.debug("Health check requested")

    # Check all services
    qdrant_status = await check_qdrant()
    llm_status = await check_llm_provider()
    embedding_status = await check_embedding_model()
    catalog_health = await source_catalog_service.health()
    catalog_block = SourceCatalogHealthBlock(
        status="healthy" if catalog_health.state == CatalogState.HEALTHY else "degraded",
        state=catalog_health.state.value,
        message=catalog_health.message,
        generated_at=catalog_health.generated_at,
        symbol_count=catalog_health.symbol_count,
        object_count=catalog_health.object_count,
        coverage_severity_summary=catalog_health.coverage_severity_summary,
    )

    # Check PostgreSQL
    db_healthy = await db.health_check()
    db_status = ServiceStatus(
        status="healthy" if db_healthy else "unavailable",
        message=f"{config.postgres_host}:{config.postgres_port}/{config.postgres_db}"
        if db_healthy
        else "Cannot connect",
    )

    # Determine overall status
    overall_status = "healthy"
    if any(s.status in ["unavailable", "error"] for s in [qdrant_status, llm_status, embedding_status, db_status]):
        overall_status = "degraded"

    # Catalog issues degrade the overall status but never produce "unhealthy"
    if catalog_block.status == "degraded" and overall_status == "healthy":
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        environment=config.environment,
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
        services={
            "database": {"status": db_status.status, "message": db_status.message or ""},
            "qdrant": {"status": qdrant_status.status, "message": qdrant_status.message or ""},
            "llm_provider": {"status": llm_status.status, "message": llm_status.message or ""},
            "embedding_model": {"status": embedding_status.status, "message": embedding_status.message or ""},
        },
        source_catalog=catalog_block,
    )


@router.get("/ping", status_code=status.HTTP_200_OK)
async def ping():
    """Simple ping endpoint"""
    return {"ping": "pong", "timestamp": datetime.now(timezone.utc)}
