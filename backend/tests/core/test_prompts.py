from types import SimpleNamespace

from app.core.prompts import PromptBuilder


def _make_retrieval_result() -> SimpleNamespace:
    return SimpleNamespace(
        authoritative=[
            {
                "source_file": "_functions\\SpellsList.js",
                "edition": "2014",
                "chunk_type": "function_definition",
                "score": 0.99,
                "content": "function ParseSpell() { return true; }",
            }
        ],
        examples=[
            {
                "source_file": "imports\\sample_spell.js",
                "edition": "2014",
                "chunk_type": "object_literal",
                "score": 0.87,
                "content": 'SpellsList["acid splash"] = { name : "Acid Splash" };',
            }
        ],
        is_empty=False,
    )


def test_build_user_prompt_includes_rag_context_and_query():
    builder = PromptBuilder()

    prompt = builder.build_user_prompt(
        query="How do I add a spell?",
        retrieval_result=_make_retrieval_result(),
        edition="2014",
    )

    assert "The user is working with the **2014** edition." in prompt
    assert "## Syntax rules and engine behavior" in prompt
    assert "## Implementation examples" in prompt
    assert "User question: How do I add a spell?" in prompt


def test_build_user_prompt_without_retrieval_returns_plain_query():
    builder = PromptBuilder()

    prompt = builder.build_user_prompt(
        query="What is AddSubClass?",
        retrieval_result=None,
        edition="2014",
    )

    assert prompt == "What is AddSubClass?"


def test_get_static_instructions_returns_default_when_settings_empty():
    builder = PromptBuilder()

    instructions = builder.get_static_instructions()

    assert "MorePurpleMoreBetter" in instructions
    assert "ES5" in instructions
    assert "## Syntax rules and engine behavior" not in instructions


def test_tool_use_addendum_absent_when_disabled(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", False)
    text = prompt_builder.get_static_instructions()
    assert "Code Verification Tools" not in text


def test_tool_use_addendum_present_when_enabled(monkeypatch):
    from app.core.prompts import prompt_builder
    from app.settings import settings

    monkeypatch.setattr(settings, "enable_tool_use", True)
    text = prompt_builder.get_static_instructions()
    assert "Code Verification Tools" in text
    assert "mpmb_read" in text
    assert "mpmb_grep" in text
    assert "mpmb_function" in text
    assert "./data/uploads/session/" in text
