"""
Shared catalog logic for curated, installable capabilities (embedding, rerank, ...)

Holds the pieces the per-capability catalogs were duplicating: the Requirement shape, the env-key presence check, and the ready/needs_key/installable status rule
Per-capability catalogs keep their own curated entry tuples and entry dataclasses; they call in here for the shared logic
"""

import importlib.util
import os
from dataclasses import dataclass

from app.config import config


@dataclass(frozen=True)
class Requirement:
    package: str  # import name to probe (e.g. "cohere")
    env_key: str | None = None  # API key env var (e.g. "COHERE_API_KEY")


def key_present(env_key: str | None) -> bool:
    """True if no key is needed, or the key is configured (config attr first, then raw env)"""
    if not env_key:
        return True
    # ? Known provider keys live on config (loaded from env at startup); stubs fall back to raw env
    attr = env_key.lower()
    if hasattr(config, attr):
        return bool(getattr(config, attr))
    return bool(os.environ.get(env_key))


def status_for(requires: Requirement | None, provider_env_key: str | None) -> str:
    """
    Availability of a catalog entry: ready | needs_key | installable

    requires: the entry's optional dependency/key requirement (None => bundled)
    provider_env_key: fallback API-key env var for the entry's provider (None => no key needed)
    """
    package = requires.package if requires else None
    if package is not None and importlib.util.find_spec(package) is None:
        return "installable"
    env_key = requires.env_key if requires else provider_env_key
    return "ready" if key_present(env_key) else "needs_key"
