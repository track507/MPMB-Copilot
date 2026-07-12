"""
ApiKey model defaults
"""

from app.model.orm import ApiKey


def test_api_key_defaults():
    key = ApiKey(name="ops", token_hash="a" * 64, token_prefix="mpmb_abc1234", scopes=["index:write"])
    assert key.__tablename__ == "api_keys"
    assert key.expires_at is None
    assert key.last_used_at is None
    assert key.revoked_at is None
