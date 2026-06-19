"""
Curated catalog of selectable reranker (cross-encoder) models

Rerankers have no vector-space dimension to match, so entries are simpler than embeddings
"""

import importlib.util
import os
from dataclasses import dataclass

from app.config import config
from app.core.embedding_catalog import Requirement  # * reuse the shared requirement shape
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RerankModel:
    provider: str
    id: str
    label: str
    requires: Requirement | None = None  # None => bundled dependency
    pinned: bool = False


# ? Provider -> API key env var for bundled (non-stub) providers
_PROVIDER_ENV_KEY: dict[str, str | None] = {
    "fastembed": None,
    "sbert": None,
    "cohere": "COHERE_API_KEY",
}

# * Curated now (zero new deps); the pinned default cannot be uninstalled
# ? All local entries are fastembed-supported cross-encoders; the run_eval A/B picks the winner on our code corpus
CATALOG: tuple[RerankModel, ...] = (
    RerankModel("fastembed", "Xenova/ms-marco-MiniLM-L-6-v2", "MS-MARCO MiniLM L6 (fast)", pinned=True),
    RerankModel("fastembed", "Xenova/ms-marco-MiniLM-L-12-v2", "MS-MARCO MiniLM L12"),
    RerankModel("fastembed", "BAAI/bge-reranker-base", "bge-reranker-base (stronger)"),
    # ? Jina v2 is multilingual and code-search capable - a strong hypothesis for MPMB's ES5/AcroJS chunks
    RerankModel("fastembed", "jinaai/jina-reranker-v2-base-multilingual", "Jina reranker v2 (multilingual, code)"),
    # Forward-compat stubs: installable via the future add-on store
    RerankModel(
        "sbert",
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "MiniLM (sentence-transformers)",
        requires=Requirement("sentence_transformers"),
    ),
    RerankModel(
        "cohere",
        "rerank-english-v3.0",
        "Cohere rerank v3",
        requires=Requirement("cohere", "COHERE_API_KEY"),
    ),
)

_DEFAULT = CATALOG[0]


def get_entry(provider: str, model: str) -> RerankModel | None:
    for entry in CATALOG:
        if entry.provider == provider and entry.id == model:
            return entry
    return None


def _key_present(env_key: str | None) -> bool:
    if not env_key:
        return True
    # ? Known provider keys live on config (loaded from env at startup); stubs fall back to raw env
    attr = env_key.lower()
    if hasattr(config, attr):
        return bool(getattr(config, attr))
    return bool(os.environ.get(env_key))


def status_for(entry: RerankModel) -> str:
    """One of: ready | needs_key | installable"""
    package = entry.requires.package if entry.requires else None
    if package is not None and importlib.util.find_spec(package) is None:
        return "installable"
    env_key = entry.requires.env_key if entry.requires else _PROVIDER_ENV_KEY.get(entry.provider)
    return "ready" if _key_present(env_key) else "needs_key"


def serialize() -> list[dict]:
    return [
        {"provider": e.provider, "id": e.id, "label": e.label, "pinned": e.pinned, "status": status_for(e)}
        for e in CATALOG
    ]
