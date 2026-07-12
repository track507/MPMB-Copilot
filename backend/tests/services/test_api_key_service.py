"""
Pure API-key rules: liveness and token format
"""

from datetime import datetime, timedelta, timezone

from app.services.db.api_key_service import KNOWN_SCOPES, generate_raw_key, key_state

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_key_state_ok_without_expiry():
    assert key_state(NOW, None, None) == "ok"


def test_key_state_expired():
    assert key_state(NOW, NOW - timedelta(seconds=1), None) == "expired"


def test_key_state_revoked_wins_over_valid_expiry():
    assert key_state(NOW, NOW + timedelta(days=30), NOW) == "revoked"


def test_generated_key_has_prefix_and_entropy():
    raw = generate_raw_key()
    assert raw.startswith("mpmb_")
    assert len(raw) > 40
    assert generate_raw_key() != raw


def test_known_scopes_is_exactly_index_write():
    # ! No decorative scopes: the catalog grows only when a new operation gets a guard
    assert KNOWN_SCOPES == frozenset({"index:write"})
