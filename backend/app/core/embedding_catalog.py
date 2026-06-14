"""
Curated catalog of selectable embedding models

First vertical slice of the unified provider-plugin/store architecture
Each entry carries a FIXED dimension (the vector-space contract that must match the stored vectors) and
forward-compatible `requires`/status metadata so the future add-on installer can flip installable entries into one-click installs
"""

import importlib.util
import os
from dataclasses import dataclass

from app.config import config
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Requirement:
    package: str  # import name to probe (e.g. "cohere")
    env_key: str | None = None  # API key env var (e.g. "COHERE_API_KEY")


@dataclass(frozen=True)
class EmbeddingModel:
    provider: str
    id: str
    label: str
    dimension: int  # ! Fixed - defines the vector space; never user-typed
    multilingual: bool = False
    query_prefix: str = ""  # e.g. "query: " for the e5 family
    doc_prefix: str = ""  # e.g. "passage: " for the e5 family
    requires: Requirement | None = None  # None => bundled dependency
    pinned: bool = False  # default models that cannot be uninstalled


# ? Provider -> API key env var for bundled (non-stub) providers
_PROVIDER_ENV_KEY: dict[str, str | None] = {
    "fastembed": None,
    "sbert": None,
    "ollama": None,
    "openai": "OPENAI_API_KEY",
}

# * Curated now (zero new deps); pinned defaults cannot be uninstalled
CATALOG: tuple[EmbeddingModel, ...] = (
    EmbeddingModel("fastembed", "BAAI/bge-small-en-v1.5", "bge-small (English)", 384, pinned=True),
    EmbeddingModel(
        "fastembed",
        "intfloat/multilingual-e5-large",
        "multilingual-e5-large",
        1024,
        multilingual=True,
        query_prefix="query: ",
        doc_prefix="passage: ",
        pinned=True,
    ),
    EmbeddingModel("openai", "text-embedding-3-small", "OpenAI 3-small", 1536, multilingual=True),
    EmbeddingModel("openai", "text-embedding-3-large", "OpenAI 3-large", 3072, multilingual=True),
    # Forward-compat stub: installable via the future add-on store
    EmbeddingModel(
        "cohere",
        "embed-multilingual-v3.0",
        "Cohere multilingual v3",
        1024,
        multilingual=True,
        requires=Requirement("cohere", "COHERE_API_KEY"),
    ),
)

# The default selection if settings/config name an unknown model
_DEFAULT = CATALOG[0]


def get_entry(provider: str, model: str) -> EmbeddingModel | None:
    for entry in CATALOG:
        if entry.provider == provider and entry.id == model:
            return entry
    return None


def _key_present(env_key: str | None) -> bool:
    if not env_key:
        return True
    # ? Known provider keys live on config (loaded from env at startup); only stub keys fall back to raw env
    attr = env_key.lower()
    if hasattr(config, attr):
        return bool(getattr(config, attr))
    return bool(os.environ.get(env_key))


def status_for(entry: EmbeddingModel) -> str:
    """One of: ready | needs_key | installable"""
    package = entry.requires.package if entry.requires else None
    if package is not None and importlib.util.find_spec(package) is None:
        return "installable"
    env_key = entry.requires.env_key if entry.requires else _PROVIDER_ENV_KEY.get(entry.provider)
    if not _key_present(env_key):
        return "needs_key"
    return "ready"


def dimension_for(provider: str, model: str) -> int:
    entry = get_entry(provider, model)
    return entry.dimension if entry is not None else _DEFAULT.dimension


def serialize() -> list[dict]:
    return [
        {
            "provider": e.provider,
            "id": e.id,
            "label": e.label,
            "dimension": e.dimension,
            "multilingual": e.multilingual,
            "pinned": e.pinned,
            "status": status_for(e),
        }
        for e in CATALOG
    ]
