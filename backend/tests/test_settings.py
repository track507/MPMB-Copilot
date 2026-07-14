"""Tests for the hot-reloadable Settings (no disk I/O - fresh instances)."""

from app.settings import Settings


def test_cheap_model_for_anthropic_default():
    s = Settings(default_llm_provider="anthropic")
    assert s.cheap_model_for() == "claude-haiku-4-5"


def test_cheap_model_for_openai_default():
    s = Settings(default_llm_provider="openai")
    assert s.cheap_model_for() == "gpt-5.4-mini"


def test_cheap_model_for_ollama_falls_back_to_default_model_when_blank():
    s = Settings(default_llm_provider="ollama", default_model="codellama", ollama_cheap_model="")
    assert s.cheap_model_for() == "codellama"


def test_cheap_model_for_explicit_provider_overrides_default():
    s = Settings(default_llm_provider="anthropic", openai_cheap_model="custom-mini")
    assert s.cheap_model_for(provider="openai") == "custom-mini"


def test_cheap_model_for_unknown_provider_uses_default_model():
    s = Settings(default_llm_provider="anthropic", default_model="some-model")
    assert s.cheap_model_for(provider="mystery") == "some-model"


def test_rerank_defaults_and_roundtrip():
    s = Settings()
    assert s.rerank_enabled is True
    assert s.rerank_provider == "fastembed"
    assert s.rerank_model == "Xenova/ms-marco-MiniLM-L-6-v2"
    assert s.rerank_candidate_k == 24
    # hot-reload overlay applies, like retrieval_mode
    s._apply({"rerank_enabled": False, "rerank_candidate_k": 32})
    assert s.rerank_enabled is False
    assert s.rerank_candidate_k == 32


def test_cheap_model_fields_serialized_in_to_dict():
    s = Settings()
    data = s.to_dict()
    assert "anthropic_cheap_model" in data
    assert "openai_cheap_model" in data
    assert "ollama_cheap_model" in data


def test_settings_update_schema_accepts_cheap_model_fields():
    from app.api.settings import SettingsUpdate

    body = SettingsUpdate(anthropic_cheap_model="claude-haiku-pinned")
    updates = body.model_dump(exclude_none=True)
    assert updates == {"anthropic_cheap_model": "claude-haiku-pinned"}


def test_embedding_dim_derives_from_catalog():
    s = Settings(embedding_provider="fastembed", embedding_model="intfloat/multilingual-e5-large")
    assert s.embedding_dim() == 1024


def test_embedding_dim_defaults_for_unknown_model():
    s = Settings(embedding_provider="fastembed", embedding_model="nope")
    assert s.embedding_dim() == 384


def test_settings_update_schema_accepts_rerank_fields():
    from app.api.settings import SettingsUpdate

    body = SettingsUpdate(rerank_enabled=True, rerank_model="BAAI/bge-reranker-base")
    updates = body.model_dump(exclude_none=True)
    assert updates == {"rerank_enabled": True, "rerank_model": "BAAI/bge-reranker-base"}


def test_auth_session_settings_defaults():
    s = Settings()
    assert s.session_lifetime_days == 30
    assert s.session_idle_days == 7


def test_inference_device_default_and_roundtrip():
    s = Settings()
    assert s.inference_device == "cpu"
    s._apply({"inference_device": "gpu"})
    assert s.inference_device == "gpu"
    assert s.to_dict()["inference_device"] == "gpu"


def test_settings_update_schema_validates_inference_device():
    import pytest
    from pydantic import ValidationError

    from app.api.settings import SettingsUpdate

    assert SettingsUpdate(inference_device="gpu").model_dump(exclude_none=True) == {"inference_device": "gpu"}
    with pytest.raises(ValidationError):
        SettingsUpdate(inference_device="tpu")
