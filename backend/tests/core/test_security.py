from app.core import security


def test_hash_and_verify_roundtrip():
    h = security.hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert security.verify_password(h, "correct horse battery") is True
    assert security.verify_password(h, "wrong password!!") is False


def test_verify_never_raises_on_garbage_hash():
    assert security.verify_password("not-a-hash", "anything") is False


def test_dummy_verify_runs():
    # ? timing pad for unknown usernames; must not raise
    security.dummy_verify()


def test_token_generate_and_hash():
    raw = security.generate_token()
    assert len(raw) >= 43  # token_urlsafe(32)
    digest = security.hash_token(raw)
    assert len(digest) == 64
    assert digest == security.hash_token(raw)  # deterministic
    assert digest != security.hash_token(security.generate_token())
