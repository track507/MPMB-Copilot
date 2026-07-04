from datetime import datetime, timedelta, timezone

from app.services.db.auth_service import session_state


def _now() -> datetime:
    return datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_session_state_ok():
    now = _now()
    assert session_state(now, now + timedelta(days=1), now - timedelta(hours=1), idle_days=7) == "ok"


def test_session_state_expired_absolute():
    now = _now()
    assert session_state(now, now - timedelta(seconds=1), now, idle_days=7) == "expired"


def test_session_state_idle():
    now = _now()
    assert session_state(now, now + timedelta(days=10), now - timedelta(days=8), idle_days=7) == "idle"


def test_session_state_idle_boundary_ok():
    now = _now()
    assert session_state(now, now + timedelta(days=10), now - timedelta(days=6, hours=23), idle_days=7) == "ok"
