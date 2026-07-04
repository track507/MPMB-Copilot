"""
Auth primitives: argon2id password hashing and opaque session tokens

Every hard operation delegates to a battle-tested implementation (argon2-cffi, stdlib secrets/hashlib);
this module is thin glue with a stable surface
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

_hasher = PasswordHasher()

# ? Pre-computed pad so login timing is uniform for unknown vs known usernames
_DUMMY_HASH = _hasher.hash("mpmb-dummy-timing-pad")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (Argon2Error, InvalidHashError, ValueError):
        return False


def dummy_verify() -> None:
    # ! Intentionally ignore the result; this exists purely to equalize timing
    verify_password(_DUMMY_HASH, "mpmb-dummy-timing-probe")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
