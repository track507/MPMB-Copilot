"""
Which credential each generation provider resolves to
"""

from app.config import config
from app.services.llm.credentials import api_key_for


def test_each_keyed_provider_resolves_its_own_key(monkeypatch):
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant")
    monkeypatch.setattr(config, "openai_api_key", "sk-oai")
    assert api_key_for("anthropic") == "sk-ant"
    assert api_key_for("openai") == "sk-oai"


def test_ollama_needs_no_key(monkeypatch):
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant")
    assert api_key_for("ollama") is None


def test_an_unknown_provider_is_none_rather_than_a_raise():
    assert api_key_for("nope") is None
