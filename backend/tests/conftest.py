"""
Shared backend test fixtures.
"""

from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_catalog_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "test_catalog.json"


@pytest.fixture
def malformed_catalog_path(tmp_path: Path) -> Path:
    """Truncated JSON; never committed."""
    p = tmp_path / "malformed.json"
    p.write_text("{")
    return p


@pytest.fixture
def wrong_shape_catalog_path(tmp_path: Path) -> Path:
    """Top-level array; invalid shape."""
    p = tmp_path / "wrong_shape.json"
    p.write_text('["not", "a", "catalog"]')
    return p


@pytest.fixture
def missing_catalog_path(tmp_path: Path) -> Path:
    return tmp_path / "does_not_exist.json"


@pytest.fixture(autouse=True)
def _bypass_auth_wall():
    from app.api.deps import Principal, current_principal, principal_or_service
    from app.main import app

    app.dependency_overrides[current_principal] = lambda: Principal(user_id="default", role="admin")
    app.dependency_overrides[principal_or_service] = lambda: Principal(user_id="default", role="admin")
    yield
    app.dependency_overrides.pop(current_principal, None)
    app.dependency_overrides.pop(principal_or_service, None)
