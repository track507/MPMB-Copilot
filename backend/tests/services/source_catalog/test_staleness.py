"""
Tests for staleness check + TTL caching
"""

from unittest.mock import patch

import pytest

from app.model.schemas.source_catalog import CatalogState, RepoProvenance
from app.services.source_catalog import SourceCatalogService
from app.services.source_catalog import staleness as staleness_module
from app.services.source_catalog.staleness import (
    StalenessTTLCache,
    check_staleness,
)


def _provenance(commit: str = "aaaaaaa") -> RepoProvenance:
    return RepoProvenance(
        branch="main",
        commit=commit,
        short_commit=commit[:7],
        date="2026-01-01",
        subject="t",
        refs="r",
        remote="x",
    )


def test_healthy_when_commits_match() -> None:
    repos = {"mpmb_source": _provenance("aaaaaaa")}
    with patch("app.services.source_catalog.staleness._git_rev_parse_head", return_value="aaaaaaa"):
        state, live = check_staleness(repos)
    assert state == CatalogState.HEALTHY
    assert live == {"mpmb_source": "aaaaaaa"}


def test_stale_when_commits_differ() -> None:
    repos = {"mpmb_source": _provenance("aaaaaaa")}
    with patch("app.services.source_catalog.staleness._git_rev_parse_head", return_value="bbbbbbb"):
        state, live = check_staleness(repos)
    assert state == CatalogState.STALE


def test_cannot_verify_keeps_healthy() -> None:
    repos = {"mpmb_source": _provenance("aaaaaaa")}
    with patch("app.services.source_catalog.staleness._git_rev_parse_head", return_value=None):
        state, live = check_staleness(repos)
    assert state == CatalogState.HEALTHY  # not downgraded
    assert live == {}


def test_ttl_cache_hits_within_window() -> None:
    cache = StalenessTTLCache(ttl_seconds=60.0)
    repos = {"mpmb_source": _provenance("aaaaaaa")}

    call_count = {"n": 0}

    def fake_check(_repos):
        call_count["n"] += 1
        return CatalogState.HEALTHY, {"mpmb_source": "aaaaaaa"}

    with patch("app.services.source_catalog.staleness.check_staleness", side_effect=fake_check):
        cache.get_or_compute(repos)
        cache.get_or_compute(repos)
        cache.get_or_compute(repos)
    assert call_count["n"] == 1


def test_ttl_cache_recomputes_after_window(monkeypatch) -> None:
    cache = StalenessTTLCache(ttl_seconds=0.0)  # always expired
    repos = {"mpmb_source": _provenance("aaaaaaa")}
    call_count = {"n": 0}

    def fake_check(_repos):
        call_count["n"] += 1
        return CatalogState.HEALTHY, {}

    with patch("app.services.source_catalog.staleness.check_staleness", side_effect=fake_check):
        cache.get_or_compute(repos)
        cache.get_or_compute(repos)
    assert call_count["n"] == 2


def test_explicit_invalidate_bypasses_ttl() -> None:
    cache = StalenessTTLCache(ttl_seconds=60.0)
    repos = {"mpmb_source": _provenance("aaaaaaa")}
    call_count = {"n": 0}

    def fake_check(_repos):
        call_count["n"] += 1
        return CatalogState.HEALTHY, {}

    with patch("app.services.source_catalog.staleness.check_staleness", side_effect=fake_check):
        cache.get_or_compute(repos)
        cache.invalidate()
        cache.get_or_compute(repos)
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_health_recomputes_staleness_when_ttl_expired(monkeypatch, valid_catalog_path):
    """health() must call the TTL cache; if the cache says expired, recompute."""
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))
    svc = SourceCatalogService()
    svc.load()

    # Force the cache to expire on every call.
    svc._staleness_cache._ttl = 0.0

    call_count = {"n": 0}
    real_check = staleness_module.check_staleness

    def counting(repos):
        call_count["n"] += 1
        return real_check(repos)

    monkeypatch.setattr(staleness_module, "check_staleness", counting)

    await svc.health()
    await svc.health()
    assert call_count["n"] >= 2
