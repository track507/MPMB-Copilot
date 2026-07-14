"""
Local models follow the inference_device setting and hot-reload when it flips
"""

from app.services.embedding.service import EmbeddingService
from app.settings import settings


def test_fastembed_provider_passes_providers_when_gpu(monkeypatch):
    from app.services.embedding.providers import fastembed as fe

    captured: dict = {}

    class FakeTextEmbedding:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(fe, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(fe, "onnx_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"])
    fe.FastEmbedProvider(model="BAAI/bge-small-en-v1.5")
    assert captured["providers"] == ["DmlExecutionProvider", "CPUExecutionProvider"]


def test_fastembed_provider_omits_providers_on_cpu(monkeypatch):
    from app.services.embedding.providers import fastembed as fe

    captured: dict = {}

    class FakeTextEmbedding:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(fe, "TextEmbedding", FakeTextEmbedding)
    monkeypatch.setattr(fe, "onnx_providers", lambda: None)
    fe.FastEmbedProvider(model="BAAI/bge-small-en-v1.5")
    assert "providers" not in captured


def test_embedding_service_reloads_when_device_flips(monkeypatch):
    service = EmbeddingService()
    loads: list[str] = []
    monkeypatch.setattr(service, "_load_provider", lambda: loads.append("load") or object())
    monkeypatch.setattr(settings, "inference_device", "cpu")
    service._ensure_provider()
    service._ensure_provider()
    assert len(loads) == 1  # cached
    monkeypatch.setattr(settings, "inference_device", "gpu")
    service._ensure_provider()
    assert len(loads) == 2  # device change invalidates the cache
