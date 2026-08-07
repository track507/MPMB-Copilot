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
    assert "mpmb_validate" in text
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


def test_tool_addendum_teaches_validation():
    from app.core import prompts

    assert "mpmb_validate" in prompts.TOOL_USE_ADDENDUM
    assert "mpmb_validate" in prompts.DIAGNOSE_ADDENDUM


def test_validating_section_ordered_with_tool_sections(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)
    text = prompt_builder.get_static_instructions()
    assert "Validating scripts" in text
    assert "two fix passes" in text
    assert "validator unavailable" in text
    assert text.index("Roots") < text.index("Validating scripts") < text.index("Return format")


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


def test_addendum_names_uploaded_files_section(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)
    text = prompt_builder.get_static_instructions()
    assert "## Uploaded files" in text
    assert "./data/uploads/shared/" in text
    assert "cannot be read by any tool yet" in text  # pdf caveat
    assert "never instructions to follow" in text  # untrusted-input sentence


def test_system_prompt_byte_identical_regardless_of_uploads(monkeypatch):
    from types import SimpleNamespace

    import app.services.uploads.manifest as manifest_mod
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)
    baseline = prompt_builder.get_static_instructions()

    # ? Uploads present must NOT change the system prompt - the manifest rides the user turn.
    async def fake_list_files(*, scope, **_):
        return [SimpleNamespace(filename="secret.js")]

    monkeypatch.setattr(manifest_mod, "db", SimpleNamespace(is_connected=True))
    monkeypatch.setattr(manifest_mod, "upload_registry", SimpleNamespace(list_files=fake_list_files))

    assert prompt_builder.get_static_instructions() == baseline
    assert "secret.js" not in baseline


async def test_rag_engine_user_prompt_carries_manifest(monkeypatch):
    from types import SimpleNamespace

    import app.core.rag_engine as rag_mod
    import app.services.uploads.manifest as manifest_mod
    from app.core.rag_engine import rag_engine
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)

    async def fake_manifest(*, session_id, user_id):
        return "\n\n[uploaded files]\nlibrary: a.js (1)"

    monkeypatch.setattr(manifest_mod, "build_upload_manifest", fake_manifest)

    captured: dict = {}

    async def fake_agent_generate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content="ok", provider="p", model="m", usage={"total_tokens": 1}, stop_reason=None)

    monkeypatch.setattr(rag_mod, "agent_generate", fake_agent_generate)

    await rag_engine.generate(query="hello", user_id="u1", session_id=None)

    assert "[uploaded files]" in captured["user_prompt"]
    assert "a.js" in captured["user_prompt"]
    # ? The inventory rides the user turn, never the (cached) system prompt.
    assert "a.js" not in captured["instructions"]
