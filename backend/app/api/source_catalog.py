"""
Source catalog reload endpoint
"""

from fastapi import APIRouter

from app.model.schemas.health import SourceCatalogHealthBlock
from app.model.schemas.source_catalog import CatalogState
from app.services.source_catalog import source_catalog_service

router = APIRouter(prefix="/source-catalog", tags=["source-catalog"])


@router.post("/reload", response_model=SourceCatalogHealthBlock)
async def reload_catalog() -> SourceCatalogHealthBlock:
    health = await source_catalog_service.reload()
    return SourceCatalogHealthBlock(
        status="healthy" if health.state == CatalogState.HEALTHY else "degraded",
        state=health.state.value,
        message=health.message,
        generated_at=health.generated_at,
        symbol_count=health.symbol_count,
        object_count=health.object_count,
        coverage_severity_summary=health.coverage_severity_summary,
    )
