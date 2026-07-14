"""
FastEmbed model caches must live in the durable configured dir, never the OS temp dir

Windows purges Temp, which half-deletes model snapshots and silently breaks retrieval (fastembed skips the download but ONNX fails to load the missing file)
"""

from app.config import config


def test_cache_path_is_absolute_and_outside_temp():
    path = config.fastembed_cache_path
    assert path.is_absolute()
    assert "temp" not in str(path).lower()
    # ? Default anchors under the repo's data dir regardless of process cwd
    assert path.parts[-3:] == ("data", "models", "fastembed")


def test_fastembed_provider_passes_cache_dir(monkeypatch):
    from app.services.embedding.providers import fastembed as fe

    captured: dict = {}

    class FakeTextEmbedding:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(fe, "TextEmbedding", FakeTextEmbedding)
    fe.FastEmbedProvider(model="BAAI/bge-small-en-v1.5")
    assert captured["cache_dir"] == str(config.fastembed_cache_path)
    assert captured["model_name"] == "BAAI/bge-small-en-v1.5"
