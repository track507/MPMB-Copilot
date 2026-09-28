"""
The env adapter's resolution rules
"""

import pytest

from app.config import config
from app.services.secrets import ANTHROPIC_API_KEY, OPENAI_API_KEY, EnvSecretsProvider


@pytest.fixture
def provider() -> EnvSecretsProvider:
    return EnvSecretsProvider()


def test_resolves_a_configured_key(monkeypatch, provider):
    monkeypatch.setattr(config, "anthropic_api_key", "sk-ant-test")
    assert provider.get(ANTHROPIC_API_KEY) == "sk-ant-test"


def test_unset_key_is_none(monkeypatch, provider):
    monkeypatch.setattr(config, "anthropic_api_key", None)
    assert provider.get(ANTHROPIC_API_KEY) is None


def test_blank_key_is_none(monkeypatch, provider):
    monkeypatch.setattr(config, "openai_api_key", "")
    assert provider.get(OPENAI_API_KEY) is None


def test_an_unknown_name_does_not_reach_config(monkeypatch, provider):
    monkeypatch.setattr(config, "database_url", "postgresql://u:pw@127.0.0.1:5433/x")
    assert provider.get("database_url") is None
    assert provider.get("DATABASE_URL") is None


def test_names_are_the_env_var_spellings():
    assert ANTHROPIC_API_KEY == "ANTHROPIC_API_KEY"
    assert OPENAI_API_KEY == "OPENAI_API_KEY"
