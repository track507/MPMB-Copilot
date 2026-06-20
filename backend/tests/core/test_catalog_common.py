import pytest

from app.core import catalog_common as cc


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "openai_api_key", None, raising=False)
    # ? cohere has no config field; key_present falls through to os.environ, so no monkeypatch is needed (and pydantic rejects setting a non-field)
    yield


def test_no_requirement_no_provider_key_is_ready():
    assert cc.status_for(None, None) == "ready"


def test_provider_key_missing_is_needs_key():
    assert cc.status_for(None, "OPENAI_API_KEY") == "needs_key"


def test_missing_package_is_installable():
    req = cc.Requirement("definitely_not_installed_pkg", "COHERE_API_KEY")
    assert cc.status_for(req, None) == "installable"


def test_present_package_with_key_absent_is_needs_key():
    # ? importlib finds a stdlib module, so it reads as "installed"; the key is still missing
    req = cc.Requirement("json", "COHERE_API_KEY")
    assert cc.status_for(req, None) == "needs_key"


def test_key_present_via_config(monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "openai_api_key", "sk-test", raising=False)
    assert cc.key_present("OPENAI_API_KEY") is True
