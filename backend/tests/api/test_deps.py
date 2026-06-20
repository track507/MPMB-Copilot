import pytest

from app.api.deps import Principal, current_principal, require_admin


@pytest.mark.asyncio
async def test_default_principal_is_admin():
    p = await current_principal()
    assert isinstance(p, Principal)
    assert p.role == "admin"


@pytest.mark.asyncio
async def test_require_admin_returns_principal():
    p = await require_admin()
    assert p.role == "admin"
