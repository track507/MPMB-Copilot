"""
Provider and capability registry, the single place that knows every selectable capability

A CapabilitySpec says how to list a capability's entries and how to report the current selection
Generation, embedding, rerank, vector store, auth and compute register one, and OCR or vision would join them
The settings store UI and GET /api/capabilities consume one uniform envelope
Adding a capability is therefore a register() call, never another bespoke catalog or endpoint

This layer unifies catalog, selection and serialization, but deliberately not construction
The instance builders (embedding_service, rerank_service, get_vector_store, build_model) stay where they are
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
    compute = "compute"


@dataclass(frozen=True)
class CapabilitySpec:
    key: Capability
    label: str
    # ? "curated" lists installable entries with a status, "live_models" groups models fetched from the provider
    kind: str
    # ? Returns the entries, or a coroutine that resolves to them
    entries: Callable[[], Any]
    # ? Reads the active selection from settings or config
    current: Callable[[], dict[str, Any]]


_REGISTRY: dict[Capability, CapabilitySpec] = {}


def register(spec: CapabilitySpec) -> None:
    _REGISTRY[spec.key] = spec


def get_spec(key: Capability) -> CapabilitySpec | None:
    return _REGISTRY.get(key)


def all_specs() -> list[CapabilitySpec]:
    return list(_REGISTRY.values())


def _vector_store_entries() -> list[dict[str, Any]]:
    # ? Curated: qdrant is bundled and pinned, the others are forward-compatible stubs
    # ! Switching a store means re-indexing, since vectors do not move between them
    return [
        {"provider": "qdrant", "id": "qdrant", "label": "Qdrant (default)", "pinned": True, "status": "ready"},
        {"provider": "weaviate", "id": "weaviate", "label": "Weaviate", "pinned": False, "status": "installable"},
        {"provider": "pgvector", "id": "pgvector", "label": "pgvector", "pinned": False, "status": "installable"},
    ]


def _auth_entries() -> list[dict[str, Any]]:
    import importlib.util

    # ? Password is the pinned method and cannot be removed
    # ? OIDC turns into one click once authlib can be installed from the store
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


def _compute_entries() -> list[dict[str, Any]]:
    from app.services import onnx_device

    # ? Detection reports the runtime, meaning whether a GPU-capable onnxruntime is installed
    # ? "installable" is the hook for an installer that would add one on request
    detected = onnx_device.detect_gpu_provider()
    gpu_label = f"GPU ({detected[1]})" if detected else "GPU"
    return [
        {"provider": "local", "id": "cpu", "label": "CPU", "pinned": True, "status": "ready"},
        {
            "provider": "local",
            "id": "gpu",
            "label": gpu_label,
            "pinned": False,
            "status": "ready" if detected else "installable",
        },
    ]


def _register_builtins() -> None:
    # ? Idempotent, so every request can call it
    # ! The imports are deferred because settings and config would otherwise cycle at module load
    if _REGISTRY:
        return
    from app.config import config
    from app.core import embedding_catalog, rerank_catalog
    from app.services.llm import catalog as model_catalog
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
    register(
        CapabilitySpec(
            key=Capability.compute,
            label="Compute device",
            kind="curated",
            entries=_compute_entries,
            current=lambda: {"device": settings.inference_device},
        )
    )


async def _resolve(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def serialize_all() -> dict[str, Any]:
    """
    One envelope per capability: {label, kind, entries, current}

    Awaits the entries callable, since the generation catalog fetches from the provider
    """
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
