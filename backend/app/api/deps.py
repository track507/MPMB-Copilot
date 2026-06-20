"""
Auth dependency stubs

Single-admin no-op today: every request resolves to the default admin principal
When auth lands these resolve the real session principal and require_admin enforces the role - a dependency swap, not a re-touch. New store / settings-mutating endpoints depend on require_admin now
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


# ! No-op single admin today
_DEFAULT_ADMIN = Principal(user_id="default", role="admin")


async def current_principal() -> Principal:
    return _DEFAULT_ADMIN


async def require_admin() -> Principal:
    # ? Today every principal is the default admin; the gate is a structural placeholder for real roles
    principal = await current_principal()
    # when real roles exist: raise HTTPException(403) if principal.role != "admin"
    return principal
