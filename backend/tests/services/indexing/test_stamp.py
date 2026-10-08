import pytest

from app.config import config
from app.services.indexing import indexer as indexer_mod
from app.services.indexing.indexer import IndexingService


@pytest.fixture
def chunk_files(tmp_path, monkeypatch):
    for name in ("a.json", "b.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "chunked_output_dir", str(tmp_path))
    monkeypatch.setattr(indexer_mod.index_status_store, "save", lambda **kwargs: None)


def _service(monkeypatch, *, fail_on: str | None = None):
    service = IndexingService()
    stamps: list[bool] = []
    monkeypatch.setattr(service, "_stamp", lambda *, complete: stamps.append(complete))

    def index_file(path, task_id=None):
        if path.name == fail_on:
            raise RuntimeError("embedding provider rejected a batch")
        return {"chunks_loaded": 0, "embeddings_generated": 0, "points_uploaded": 0, "source_file": path.name}

    monkeypatch.setattr(service, "index_file", index_file)
    return service, stamps


def test_a_full_build_is_stamped_incomplete_first_and_complete_last(chunk_files, monkeypatch):
    service, stamps = _service(monkeypatch)

    service.index_all_chunks()

    assert stamps == [False, True]


def test_a_build_that_dies_is_never_stamped_complete(chunk_files, monkeypatch):
    service, stamps = _service(monkeypatch, fail_on="b.json")

    with pytest.raises(RuntimeError):
        service.index_all_chunks()

    assert stamps == [False]
