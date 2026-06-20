"""
Catalog-derived system prompt blocks + per-query hints
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.prompts import PromptBuilder
from app.services.source_catalog import SourceCatalogService


def test_build_user_prompt_includes_edition_and_query():
    builder = PromptBuilder()

    prompt = builder.build_user_prompt(
        query="How do I add a spell?",
        edition="2014",
    )

    assert "The user is working with the **2014** edition." in prompt
    assert "User question: How do I add a spell?" in prompt
    # No pre-injected retrieval sections - the agent fetches via mpmb_search
    assert "## Syntax rules and engine behavior" not in prompt
    assert "## Implementation examples" not in prompt


def test_build_user_prompt_bare_query_passes_through():
    builder = PromptBuilder()

    prompt = builder.build_user_prompt(query="What is AddSubClass?")

    assert prompt == "What is AddSubClass?"


def test_get_static_instructions_returns_default_when_settings_empty():
    builder = PromptBuilder()

    instructions = builder.get_static_instructions()

    assert "MorePurpleMoreBetter" in instructions
    assert "ES5" in instructions
    assert "## Syntax rules and engine behavior" not in instructions


def test_no_tools_addendum_when_disabled(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", False)
    text = prompt_builder.get_static_instructions()
    assert "MPMB Source Tools" not in text
    # Honest fallback: the prompt must not promise retrieval that never happens
    assert "No Tool Access" in text
    assert "never\ninvent function bodies" in text or "never invent function bodies" in text


def test_tool_use_addendum_present_when_enabled(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)
    text = prompt_builder.get_static_instructions()
    assert "MPMB Source Tools" in text
    assert "mpmb_search" in text
    assert "mpmb_read" in text
    assert "mpmb_grep" in text
    assert "mpmb_function" in text
    assert "./data/uploads/session/" in text
    assert "./data/imports_source/" in text
    assert "FIRST move" in text


def test_diagnose_addendum_present_when_tools_enabled(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)
    text = prompt_builder.get_static_instructions()
    assert "Diagnosing Errors" in text
    assert "Root cause" in text
    assert "./data/uploads/session/" in text
    # ? the playbook must come after the tools it depends on
    assert text.index("MPMB Source Tools") < text.index("Diagnosing Errors")


def test_diagnose_addendum_absent_when_tools_disabled(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", False)
    text = prompt_builder.get_static_instructions()
    assert "Diagnosing Errors" not in text


@pytest.fixture
def healthy_pb_service(monkeypatch, valid_catalog_path: Path) -> SourceCatalogService:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(valid_catalog_path))
    monkeypatch.setattr(settings_module.settings, "inject_catalog_context", True)
    monkeypatch.setattr(settings_module.settings, "system_prompt", None)
    monkeypatch.setattr(settings_module.settings, "enable_tool_use", False)
    svc = SourceCatalogService()
    svc.load()
    return svc


@pytest.fixture
def missing_pb_service(monkeypatch, tmp_path: Path) -> SourceCatalogService:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "source_catalog_enabled", True)
    monkeypatch.setattr(settings_module.settings, "source_catalog_path", str(tmp_path / "nope.json"))
    monkeypatch.setattr(settings_module.settings, "inject_catalog_context", True)
    monkeypatch.setattr(settings_module.settings, "system_prompt", None)
    monkeypatch.setattr(settings_module.settings, "enable_tool_use", False)
    svc = SourceCatalogService()
    svc.load()
    return svc


def _instructions(svc: SourceCatalogService) -> str:
    with patch("app.core.prompts.source_catalog_service", svc):
        return PromptBuilder().get_static_instructions()


def test_default_with_placeholders_renders(healthy_pb_service) -> None:
    text = _instructions(healthy_pb_service)
    assert "<<CATALOG_REGISTRIES>>" not in text
    assert "<<CATALOG_ADD_FUNCTIONS>>" not in text
    assert "MPMB OBJECT TYPES" in text
    assert "SpellsList" in text


def test_default_missing_strips_placeholders(missing_pb_service) -> None:
    text = _instructions(missing_pb_service)
    assert "<<CATALOG_REGISTRIES>>" not in text
    assert "<<CATALOG_ADD_FUNCTIONS>>" not in text


def test_custom_with_placeholders(healthy_pb_service, monkeypatch) -> None:
    from app import settings as settings_module

    custom = "Custom intro.\n\n<<CATALOG_REGISTRIES>>\n\n<<CATALOG_ADD_FUNCTIONS>>\n\nCustom outro."
    monkeypatch.setattr(settings_module.settings, "system_prompt", custom)
    text = _instructions(healthy_pb_service)
    assert "Custom intro." in text
    assert "Custom outro." in text
    assert "<<CATALOG_REGISTRIES>>" not in text
    assert "SpellsList" in text


def test_custom_without_placeholders_appends(healthy_pb_service, monkeypatch) -> None:
    from app import settings as settings_module

    custom = "Just my custom prompt with no placeholders."
    monkeypatch.setattr(settings_module.settings, "system_prompt", custom)
    text = _instructions(healthy_pb_service)
    assert "Just my custom prompt" in text
    assert "MPMB OBJECT TYPES" in text  # appendix appended
    assert "SpellsList" in text


def test_custom_without_placeholders_no_append_when_disabled(healthy_pb_service, monkeypatch) -> None:
    from app import settings as settings_module

    custom = "Just my custom prompt with no placeholders."
    monkeypatch.setattr(settings_module.settings, "system_prompt", custom)
    monkeypatch.setattr(settings_module.settings, "inject_catalog_context", False)
    text = _instructions(healthy_pb_service)
    assert "Just my custom prompt" in text
    assert "MPMB OBJECT TYPES" not in text


def test_user_prompt_includes_catalog_hints(healthy_pb_service) -> None:
    builder = PromptBuilder()
    hints = "// Resolved object type: SpellsList (matched via code_identifier)"
    user_prompt = builder.build_user_prompt(
        query="how do I add a spell?",
        edition=None,
        catalog_hints=hints,
    )
    assert hints in user_prompt
    assert "User question: how do I add a spell?" in user_prompt


def test_user_prompt_no_hints_when_none() -> None:
    builder = PromptBuilder()
    user_prompt = builder.build_user_prompt(
        query="raw query",
        edition=None,
        catalog_hints=None,
    )
    assert user_prompt == "raw query"


def test_tool_use_addendum_still_concatenated(healthy_pb_service, monkeypatch) -> None:
    from app import settings as settings_module

    monkeypatch.setattr(settings_module.settings, "enable_tool_use", True)
    text = _instructions(healthy_pb_service)
    assert "MPMB OBJECT TYPES" in text  # catalog blocks present
    assert "MPMB Source Tools" in text  # tool-use addendum present
