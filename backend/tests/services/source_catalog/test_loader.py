"""
Tests for source_catalog.loader
"""

import threading
from pathlib import Path

from app.model.schemas.source_catalog import CatalogModel, CatalogState
from app.services.source_catalog import SourceCatalogService
from app.services.source_catalog.loader import load_catalog


def test_load_valid_catalog(valid_catalog_path: Path) -> None:
    result = load_catalog(valid_catalog_path)
    assert result.state == CatalogState.HEALTHY
    assert isinstance(result.catalog, CatalogModel)
    assert result.catalog.generated_at == "2026-01-01T00:00:00Z"
    assert len(result.catalog.objects) == 8
    assert result.file_mtime is not None
    assert "loaded" in result.message.lower() or "ok" in result.message.lower()


def test_load_missing_file(missing_catalog_path: Path) -> None:
    result = load_catalog(missing_catalog_path)
    assert result.state == CatalogState.MISSING
    assert result.catalog is None
    assert "not found" in result.message.lower() or "missing" in result.message.lower()
    assert str(missing_catalog_path) in result.message


def test_load_malformed_json(malformed_catalog_path: Path) -> None:
    result = load_catalog(malformed_catalog_path)
    assert result.state == CatalogState.MALFORMED
    assert result.catalog is None
    assert "json" in result.message.lower() or "parse" in result.message.lower()


def test_load_wrong_shape(wrong_shape_catalog_path: Path) -> None:
    result = load_catalog(wrong_shape_catalog_path)
    assert result.state == CatalogState.MALFORMED
    assert result.catalog is None


def test_load_extra_unknown_fields(tmp_path: Path, valid_catalog_path: Path) -> None:
    """Pydantic extra='ignore' must accept benign analyzer additions."""
    import json

    raw = json.loads(valid_catalog_path.read_text())
    raw["future_field_we_havent_seen_yet"] = {"any": "shape"}
    raw["objects"][0]["future_per_object_field"] = "ignored"
    extended = tmp_path / "extended.json"
    extended.write_text(json.dumps(raw))

    result = load_catalog(extended)
    assert result.state == CatalogState.HEALTHY
    assert result.catalog is not None


def test_service_load_disabled_by_settings(valid_catalog_path: Path, monkeypatch) -> None:
    """source_catalog_enabled=False → state=MISSING with explicit message."""
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", False)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))

    svc = SourceCatalogService()
    health = svc.load()
    assert health.state == CatalogState.MISSING
    assert "disabled" in health.message.lower()


def test_service_atomic_swap_under_concurrent_reads(valid_catalog_path: Path, monkeypatch) -> None:
    """Reads during reload either see old or new indexes — never a half-built state."""
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))

    svc = SourceCatalogService()
    svc.load()
    stop = threading.Event()
    errors: list[str] = []

    def reader() -> None:
        while not stop.is_set():
            try:
                idx = svc.symbol_index()
                # If we ever observe an empty mapping while load is HEALTHY, that's torn read
                if idx and "SpellsList" not in idx and "AddSubClass" not in idx:
                    errors.append("torn read observed")
            except Exception as exc:
                errors.append(repr(exc))

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()

    # Hammer 10 reloads while readers spin
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        for _ in range(10):
            loop.run_until_complete(svc.reload())
    finally:
        loop.close()

    stop.set()
    for t in threads:
        t.join(timeout=2)

    assert errors == []
