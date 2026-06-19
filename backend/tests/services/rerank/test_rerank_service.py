from app.services.rerank.service import RerankService


class _StubEncoder:
    def __init__(self, scores):
        self._scores = scores

    def rerank(self, query, documents):
        # fastembed returns an iterable of floats aligned to documents
        return iter(self._scores)


def test_orders_by_score_desc_and_cuts_to_top_k(monkeypatch):
    svc = RerankService()
    monkeypatch.setattr(svc, "_ensure_model", lambda: _StubEncoder([0.1, 0.9, 0.5]))
    cands = [{"id": "a", "content": "x"}, {"id": "b", "content": "y"}, {"id": "c", "content": "z"}]
    out = svc.rerank("q", cands, top_k=2)
    assert [c["id"] for c in out] == ["b", "c"]
    assert out[0]["rerank_score"] == 0.9


def test_falls_back_to_input_order_on_error(monkeypatch):
    class _Boom:
        def rerank(self, query, documents):
            raise RuntimeError("boom")

    svc = RerankService()
    monkeypatch.setattr(svc, "_ensure_model", lambda: _Boom())
    cands = [{"id": "a"}, {"id": "b"}]
    assert [c["id"] for c in svc.rerank("q", cands, top_k=1)] == ["a"]


def test_empty_and_disabled(monkeypatch):
    svc = RerankService()
    monkeypatch.setattr(svc, "_ensure_model", lambda: None)  # provider unavailable
    assert svc.rerank("q", [], top_k=3) == []
    cands = [{"id": "a"}, {"id": "b"}]
    assert svc.rerank("q", cands, top_k=1) == cands[:1]
