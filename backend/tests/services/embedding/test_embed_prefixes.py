from app.services.embedding.service import EmbeddingService


class _Recorder:
    dimension = 3

    def __init__(self):
        self.seen: list[str] = []

    def embed_texts(self, texts):
        self.seen.extend(texts)
        return [[0.0, 0.0, 0.0] for _ in texts]


def _service(monkeypatch, provider="fastembed", model="intfloat/multilingual-e5-large"):
    from app.settings import settings

    monkeypatch.setattr(settings, "embedding_provider", provider)
    monkeypatch.setattr(settings, "embedding_model", model)
    monkeypatch.setattr(settings, "inference_device", "cpu")
    svc = EmbeddingService()
    rec = _Recorder()
    svc.provider = rec
    # ? Must mirror _ensure_provider's cache key exactly, or the recorder is evicted by a real model load
    svc._selection = (provider, model, "cpu")
    return svc, rec


def test_e5_prefixes_applied(monkeypatch):
    svc, rec = _service(monkeypatch)
    svc.embed_documents(["hello"])
    svc.embed_query("hola")
    assert "passage: hello" in rec.seen
    assert "query: hola" in rec.seen


def test_no_prefix_for_plain_model(monkeypatch):
    svc, rec = _service(monkeypatch, model="BAAI/bge-small-en-v1.5")
    svc.embed_documents(["hello"])
    svc.embed_query("hi")
    assert rec.seen == ["hello", "hi"]
