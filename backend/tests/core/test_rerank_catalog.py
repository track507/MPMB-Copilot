from app.core import rerank_catalog as rc


def test_pinned_local_default_is_ready():
    e = rc.get_entry("fastembed", "Xenova/ms-marco-MiniLM-L-6-v2")
    assert e is not None
    assert e.pinned is True
    assert rc.status_for(e) == "ready"  # local, no key needed


def test_second_fastembed_model_is_ready():
    e = rc.get_entry("fastembed", "BAAI/bge-reranker-base")
    assert e is not None
    assert rc.status_for(e) == "ready"


def test_cohere_stub_is_installable_when_dep_missing():
    # ? installable short-circuits on the missing package, before any key lookup
    e = rc.get_entry("cohere", "rerank-english-v3.0")
    assert e is not None
    assert rc.status_for(e) == "installable"


def test_sbert_entry_declares_requirement():
    e = rc.get_entry("sbert", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert e is not None
    assert e.requires is not None
    assert e.requires.package == "sentence_transformers"


def test_serialize_shape():
    rows = rc.serialize()
    assert rows
    assert set(rows[0]) == {"provider", "id", "label", "pinned", "status"}
