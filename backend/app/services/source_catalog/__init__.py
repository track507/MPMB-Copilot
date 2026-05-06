"""
Public source-catalog service

Orchestrates loader + indexes + staleness + prompt_render
Module-level singleton `source_catalog_service` is the canonical access point
"""

import asyncio
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

from app.logger import get_logger
from app.model.schemas.source_catalog import (
    CatalogHealth,
    CatalogState,
    CoverageWarning,
    ObjectTypeMatch,
    SymbolEntry,
)
from app.services.source_catalog.indexes import Indexes, build_indexes
from app.services.source_catalog.loader import LoadResult, load_catalog
from app.services.source_catalog.prompt_render import (
    deterministic_add_function_block,
    deterministic_registry_block,
)
from app.services.source_catalog.staleness import StalenessTTLCache

logger = get_logger(__name__)

_DEFAULT_CATALOG_RELATIVE = Path("scripts/analyze/reports/mpmb-analysis.json")


def _resolve_repo_root() -> Path:
    """Walk up from this file until we find the project root (the directory
    containing 'scripts/analyze/'). Falls back to cwd if not found."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "scripts" / "analyze").is_dir():
            return parent
    return Path.cwd()


def _resolve_catalog_path() -> Path:
    """Resolution order: settings → config/env → repo-root default."""
    from app.settings import settings  # local import: avoid circular at import time

    explicit = getattr(settings, "source_catalog_path", None)
    if explicit:
        return Path(explicit).resolve()

    env_path = os.environ.get("MPMB_CATALOG_PATH")
    if env_path:
        return Path(env_path).resolve()

    return (_resolve_repo_root() / _DEFAULT_CATALOG_RELATIVE).resolve()


class SourceCatalogService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: CatalogState = CatalogState.MISSING
        self._message: str = "not yet loaded"
        self._catalog_path: Path = Path()
        self._file_mtime: Optional[datetime] = None
        self._generated_at: Optional[str] = None
        self._repos: dict = {}
        self._live_repo_commits: dict[str, str] = {}
        self._indexes: Optional[Indexes] = None
        self._registry_block: str = ""
        self._add_function_block: str = ""
        self._last_staleness_check: Optional[datetime] = None
        self._staleness_cache = StalenessTTLCache(ttl_seconds=60.0)

    # Public API

    def load(self) -> CatalogHealth:
        """Idempotent. Called once from FastAPI lifespan startup. Never raises."""
        from app.settings import settings

        if not getattr(settings, "source_catalog_enabled", True):
            with self._lock:
                self._state = CatalogState.MISSING
                self._message = "missing — disabled by settings"
                self._catalog_path = _resolve_catalog_path()
            return self._snapshot_health()

        path = _resolve_catalog_path()
        result = load_catalog(path)
        self._apply_load_result(path, result)
        return self._snapshot_health()

    async def reload(self) -> CatalogHealth:
        """Force re-parse + index rebuild via to_thread. Atomic swap under lock."""
        from app.settings import settings

        if not getattr(settings, "source_catalog_enabled", True):
            with self._lock:
                self._state = CatalogState.MISSING
                self._message = "missing — disabled by settings"
                self._indexes = None
                self._registry_block = ""
                self._add_function_block = ""
            return self._snapshot_health()

        self._staleness_cache.invalidate()
        path = _resolve_catalog_path()
        result = await asyncio.to_thread(load_catalog, path)
        self._apply_load_result(path, result, trigger="explicit")
        return self._snapshot_health()

    async def health(self) -> CatalogHealth:
        """
        Cheap
        Checks mtime; reloads if changed
        Refreshes staleness on TTL cadence
        """
        path = self._catalog_path or _resolve_catalog_path()
        if path.exists():
            try:
                current_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                current_mtime = None
            if current_mtime is not None and current_mtime != self._file_mtime:
                logger.info("source_catalog_mtime_changed", path=str(path))
                await self.reload()

        await self._refresh_staleness_if_due()
        return self._snapshot_health()

    def has_data(self) -> bool:
        return self._state in (CatalogState.HEALTHY, CatalogState.STALE) and self._indexes is not None

    def symbol_index(self) -> Mapping[str, SymbolEntry]:
        idx = self._indexes
        if idx is None:
            return {}
        return idx.symbols

    def registry_names(self) -> tuple[str, ...]:
        idx = self._indexes
        if idx is None:
            return ()
        return idx.registry_names

    def find_object_type(self, query: str) -> Optional[ObjectTypeMatch]:
        idx = self._indexes
        if idx is None:
            return None
        return idx.find_object_type(query)

    def coverage_warnings(self) -> list[CoverageWarning]:
        idx = self._indexes
        if idx is None:
            return []
        return list(idx.coverage_warnings)

    def static_prompt_blocks(self) -> tuple[str, str]:
        return self._registry_block, self._add_function_block

    # Internals

    def _apply_load_result(
        self,
        path: Path,
        result: LoadResult,
        *,
        trigger: str = "load",
    ) -> None:
        if result.catalog is None:
            with self._lock:
                self._state = result.state
                self._message = result.message
                self._catalog_path = path
                self._file_mtime = result.file_mtime
                self._generated_at = None
                self._repos = {}
                self._live_repo_commits = {}
                self._indexes = None
                self._registry_block = ""
                self._add_function_block = ""
            logger.warning(
                "source_catalog_unavailable",
                state=result.state.value,
                path=str(path),
                message=result.message,
            )
            return

        new_indexes = build_indexes(result.catalog)
        new_registry_block = deterministic_registry_block(new_indexes)
        new_add_block = deterministic_add_function_block(new_indexes)
        staleness_state, live_commits = self._staleness_cache.get_or_compute(result.catalog.repos)
        final_state = CatalogState.STALE if staleness_state == CatalogState.STALE else CatalogState.HEALTHY

        with self._lock:
            self._state = final_state
            self._message = result.message
            self._catalog_path = path
            self._file_mtime = result.file_mtime
            self._generated_at = result.catalog.generated_at
            self._repos = result.catalog.repos
            self._live_repo_commits = live_commits
            self._indexes = new_indexes
            self._registry_block = new_registry_block
            self._add_function_block = new_add_block
            self._last_staleness_check = datetime.now(tz=timezone.utc)

        logger.info(
            "source_catalog_loaded",
            state=final_state.value,
            generated_at=result.catalog.generated_at,
            object_count=new_indexes.object_count,
            symbol_count=new_indexes.symbol_count,
            coverage_high_count=new_indexes.coverage_severity_summary.get("high", 0),
            trigger=trigger,
        )

    def _snapshot_health(self) -> CatalogHealth:
        idx = self._indexes
        return CatalogHealth(
            state=self._state,
            message=self._message,
            catalog_path=str(self._catalog_path),
            file_mtime=self._file_mtime,
            generated_at=self._generated_at,
            repos=dict(self._repos),
            live_repo_commits=dict(self._live_repo_commits),
            object_count=idx.object_count if idx else 0,
            symbol_count=idx.symbol_count if idx else 0,
            coverage_severity_summary=(
                dict(idx.coverage_severity_summary) if idx else {"high": 0, "medium": 0, "low": 0}
            ),
            last_staleness_check=self._last_staleness_check,
        )

    async def _refresh_staleness_if_due(self) -> None:
        """
        Re-evaluate staleness via the TTL cache.
        No file re-parse; just compares captured catalog commits to live git HEAD again (cheap when within the TTL window)
        """
        if self._indexes is None or not self._repos:
            return
        new_state, live = await asyncio.to_thread(self._staleness_cache.get_or_compute, dict(self._repos))
        with self._lock:
            # Only flip between HEALTHY and STALE; don't override MISSING/MALFORMED.
            if self._state in (CatalogState.HEALTHY, CatalogState.STALE):
                self._state = new_state
            self._live_repo_commits = dict(live)
            self._last_staleness_check = datetime.now(tz=timezone.utc)


source_catalog_service = SourceCatalogService()
