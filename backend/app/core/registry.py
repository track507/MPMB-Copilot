"""
Provider/capability registry - the single place that knows every selectable capability

Each capability (generation, embedding, rerank, vector store, and future OCR/vision) registers a CapabilitySpec describing how to list its selectable entries and report the current selection
The settings store UI and the /capabilities endpoint consume one uniform envelope, so adding a capability is a register() call - never a new bespoke catalog or endpoint

This layer unifies catalog / selection / serialization
It deliberately does NOT replace the working instance builders (embedding_service, rerank_service, get_vector_store, build_model); folding those in is a later tightening, out of the consolidation-phase scope
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Capability(str, Enum):
    generation = "generation"
    embedding = "embedding"
    rerank = "rerank"
    vector_store = "vector_store"
    auth = "auth"


@dataclass(frozen=True)
class CapabilitySpec:
    key: Capability
    label: str
    kind: str  # "curated" (installable entries w/ status) | "live_models" (provider-grouped, fetched live)
    entries: Callable[[], Any]  # returns the entries, or a coroutine that resolves to them
    current: Callable[[], dict]  # the active selection, read from settings/config


_REGISTRY: dict[Capability, CapabilitySpec] = {}


def register(spec: CapabilitySpec) -> None:
    _REGISTRY[spec.key] = spec


def get_spec(key: Capability) -> CapabilitySpec | None:
    return _REGISTRY.get(key)


def all_specs() -> list[CapabilitySpec]:
    return list(_REGISTRY.values())


def _vector_store_entries() -> list[dict]:
    # ? Curated: qdrant is bundled/pinned; others are forward-compat stubs. Switching a store rebuilds the index
    return [
        {"provider": "qdrant", "id": "qdrant", "label": "Qdrant (default)", "pinned": True, "status": "ready"},
        {"provider": "weaviate", "id": "weaviate", "label": "Weaviate", "pinned": False, "status": "installable"},
        {"provider": "pgvector", "id": "pgvector", "label": "pgvector", "pinned": False, "status": "installable"},
    ]


def _auth_entries() -> list[dict]:
    import importlib.util

    # ? Password is the pinned, non-removable method; OIDC becomes one-click once authlib is installable via the store
    oidc_status = "ready" if importlib.util.find_spec("authlib") is not None else "installable"
    return [
        {"provider": "local", "id": "password", "label": "Username & password", "pinned": True, "status": "ready"},
        {
            "provider": "oidc",
            "id": "oidc",
            "label": "OIDC / SSO (Keycloak, Authentik, Zitadel, ...)",
            "pinned": False,
            "status": oidc_status,
        },
    ]


def _register_builtins() -> None:
    # ? Idempotent; deferred imports avoid settings/config import cycles at module load
    if _REGISTRY:
        return
    from app.config import config
    from app.core import embedding_catalog, model_catalog, rerank_catalog
    from app.settings import settings

    register(
        CapabilitySpec(
            key=Capability.generation,
            label="Generation (LLM)",
            kind="live_models",
            entries=lambda: model_catalog.get_model_catalog(),
            current=lambda: {
                "provider": settings.default_llm_provider,
                "model": settings.default_model,
                "effort": settings.default_effort,
            },
        )
    )
    register(
        CapabilitySpec(
            key=Capability.embedding,
            label="Embedding",
            kind="curated",
            entries=lambda: embedding_catalog.serialize(),
            current=lambda: {"provider": settings.embedding_provider, "model": settings.embedding_model},
        )
    )
    register(
        CapabilitySpec(
            key=Capability.rerank,
            label="Reranker",
            kind="curated",
            entries=lambda: rerank_catalog.serialize(),
            current=lambda: {
                "provider": settings.rerank_provider,
                "model": settings.rerank_model,
                "enabled": settings.rerank_enabled,
                "candidate_k": settings.rerank_candidate_k,
            },
        )
    )
    register(
        CapabilitySpec(
            key=Capability.vector_store,
            label="Vector store",
            kind="curated",
            entries=_vector_store_entries,
            current=lambda: {"provider": getattr(config, "vector_store", "qdrant")},
        )
    )
    register(
        CapabilitySpec(
            key=Capability.auth,
            label="Authentication",
            kind="curated",
            entries=_auth_entries,
            current=lambda: {"method": "password"},
        )
    )


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def serialize_all() -> dict[str, Any]:
    """One envelope per capability: {label, kind, entries, current}. Awaits live fetches (generation)"""
    _register_builtins()
    out: dict[str, Any] = {}
    for spec in all_specs():
        out[spec.key.value] = {
            "label": spec.label,
            "kind": spec.kind,
            "entries": await _resolve(spec.entries()),
            "current": spec.current(),
        }
    return out
