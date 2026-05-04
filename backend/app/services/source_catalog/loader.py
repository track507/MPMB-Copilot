"""Loads and validates the analyzer-generated source catalog JSON."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from app.logger import get_logger
from app.model.schemas.source_catalog import CatalogModel, CatalogState

logger = get_logger(__name__)


@dataclass(frozen=True)
class LoadResult:
    """Outcome of a catalog load attempt. Never raises; always returns a result."""

    state: CatalogState
    catalog: Optional[CatalogModel]
    message: str
    file_mtime: Optional[datetime]


def load_catalog(path: Path) -> LoadResult:
    """Parse + validate a catalog JSON file. Pure function; never raises."""
    if not path.exists():
        return LoadResult(
            state=CatalogState.MISSING,
            catalog=None,
            message=f"catalog not found at {path}",
            file_mtime=None,
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except (PermissionError, OSError) as exc:
        logger.error("source_catalog_read_failed", path=str(path), error=str(exc))
        return LoadResult(
            state=CatalogState.MALFORMED,
            catalog=None,
            message=f"could not read {path}: {exc}",
            file_mtime=None,
        )

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("source_catalog_json_parse_failed", path=str(path), error=str(exc))
        return LoadResult(
            state=CatalogState.MALFORMED,
            catalog=None,
            message=f"json parse error in {path}: {exc.msg} at line {exc.lineno}",
            file_mtime=None,
        )

    try:
        catalog = CatalogModel.model_validate(raw)
    except ValidationError as exc:
        first_three = exc.errors()[:3]
        summary = "; ".join(f"{e['loc']}: {e['msg']}" for e in first_three)
        logger.error("source_catalog_validation_failed", path=str(path), errors=summary)
        return LoadResult(
            state=CatalogState.MALFORMED,
            catalog=None,
            message=f"validation error in {path}: {summary}",
            file_mtime=None,
        )

    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return LoadResult(
        state=CatalogState.HEALTHY,
        catalog=catalog,
        message=f"catalog loaded ok from {path}",
        file_mtime=mtime,
    )
