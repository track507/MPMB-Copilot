"""Prompt construction for MPMB-Copilot RAG pipeline.

Builds the two-layer system prompt:
    1. **Static instructions** (cacheable) - MPMB rules, ES5 constraints,
                object type reference, edition awareness.  Stays identical across
                turns in a conversation so Anthropic's prompt caching applies.
    2. **Dynamic RAG context** (per-query) - formatted authoritative and
                example chunks from the retriever.  Changes each turn.

The prompt builder produces raw message dicts (not LangChain Message
objects) so that `cache_control` keys can be attached for Anthropic.
Other providers ignore the extra key harmlessly.

The static instructions text is stored in `settings.system_prompt`.
When that field is None/empty, the built-in default is used.  The
frontend can later let users edit this via `PATCH /api/settings`.

Usage:
    from app.core.prompts import prompt_builder

    messages = prompt_builder.build_messages(
        query="How do I add a spell?",
        retrieval_result=result,
        conversation_history=[...],
        edition="2014",
    )
    # -> list of message dicts ready for LLM client
"""

from typing import Optional

from app.core.retriever import RetrievalResult
from app.logger import get_logger
from app.settings import settings

logger = get_logger(__name__)

# * Default static system prompt
DEFAULT_SYSTEM_PROMPT = """\
You are an expert assistant for writing automation code for \
MorePurpleMoreBetter's D&D 5e Character Record Sheet.  You write \
Adobe Acrobat JavaScript (ECMAScript 5).

CRITICAL ES5 CONSTRAINTS - violating these will cause runtime errors:
- Use `var` for ALL variable declarations.  Never use `let` or `const`.
- No arrow functions.  Use `function(x) { }` syntax only.
- No template literals.  Use string concatenation with `+`.
- No destructuring, spread/rest, default parameters, or classes.
- No `for...of` loops.  Use `for (var i = 0; ...)` or `.forEach()`.
- No Promises, async/await, or generators.
- Use `console.println()` for console output, NOT `console.log()`.
- All code runs in Adobe Acrobat's JavaScript engine, not Node.js or browsers.

MPMB OBJECT TYPES you can create or modify:
- SpellsList["key"] = { ... }           - Spells
- ClassList["key"] = { ... }            - Classes
- ClassSubList["key"] = { ... }         - Subclasses (or use AddSubClass)
- RaceList["key"] = { ... }             - Races / Species
- FeatsList["key"] = { ... }            - Feats
- MagicItemsList["key"] = { ... }       - Magic items
- CreatureList["key"] = { ... }         - Creatures / Wild shapes
- BackgroundList["key"] = { ... }       - Backgrounds
- BackgroundFeatureList["key"] = { ... } - Background features
- WeaponsList["key"] = { ... }          - Weapons
- ArmourList["key"] = { ... }           - Armor
- AmmoList["key"] = { ... }             - Ammunition
- GearList["key"] = { ... }             - Adventuring gear
- SourceList["key"] = { ... }           - Source books
- CompanionList["key"] = { ... }        - Companion templates
- PacksList["key"] = { ... }            - Equipment packs

MPMB ADD FUNCTIONS (alternative to direct object assignment):
- AddSubClass("parentClass", "subclassKey", { ... })
- AddFeatureChoice("parentKey", "featureKey", { ... })
- AddRacialVariant("parentRace", "variantKey", { ... })
- AddBackgroundVariant("parentBG", "variantKey", { ... })
- AddWarlockInvocation("invocationKey", { ... })
- AddFightingStyle("styleKey", { ... })

FILE HEADER - every import file needs:
- var iFileName = "filename.js";
- RequiredSheetVersion("13.0.6");  // or "24.0.5" for 2024 edition

WHEN WRITING CODE:
1. Always provide complete, copy-pasteable code.
2. Include the file header (iFileName, RequiredSheetVersion).
3. Include ALL required attributes - check the syntax rules provided.
4. Use comments to explain non-obvious attributes.
5. Cite which source files your examples come from when relevant.
6. Match the user's edition (2014 or 2024) for attribute syntax.

GROUNDING IN PROVIDED CONTEXT:
The chat backend retrieves relevant MPMB source code, syntax templates, \
and engine function definitions on every turn and injects them into your \
system message under "Syntax rules and engine behavior" and "Implementation \
examples" sections.

- Treat that retrieved context as your primary source of truth.  When the \
	user asks about an engine function (e.g. CreateSpellList, ParseSpell, \
	AddSubClass, etc.) or about valid attributes, look in the retrieved \
	sections FIRST and quote / cite from them directly.
- If the user asks for a specific function's implementation and that \
	function IS present in the retrieved context, reproduce it from the \
	context.  Do not claim you lack access.
- If the requested function or attribute is NOT in the retrieved context, \
	say exactly that ("That function isn't in my retrieved context for this \
	query") rather than refusing in general terms or guessing.  You may then \
	suggest the user re-ask with a more specific phrasing or point them to \
	the upstream MPMB repository.
- Never describe yourself as an LLM that lacks access to MPMB internals - \
	the engine source IS indexed and retrievable; missing results mean the \
	retriever didn't surface a match for this particular query, not that the \
	source is unavailable."""


# RAG context formatting
def _format_chunk(chunk: dict, index: int) -> str:
    """Format a single retrieval result for prompt injection."""
    source = chunk.get("source_file", "unknown")
    edition = chunk.get("edition", "?")
    chunk_type = chunk.get("chunk_type", "")
    score = chunk.get("score", 0.0)
    content = chunk.get("content", "")

    # Metadata line for provenance
    meta_parts = [f"[{index}]", f"({edition})"]
    if chunk_type:
        meta_parts.append(chunk_type)
    meta_parts.append(f"from {source}")
    meta_parts.append(f"relevance={score:.2f}")

    header = " ".join(meta_parts)

    return f"// {header}\n{content}"


def _format_chunk_section(chunks: list[dict], section_title: str) -> str:
    """Format a list of chunks into a labeled prompt section."""
    if not chunks:
        return ""

    formatted = [f"## {section_title}"]
    for i, chunk in enumerate(chunks, 1):
        formatted.append(_format_chunk(chunk, i))

    return "\n\n".join(formatted)


# * Message construction
class PromptBuilder:
    """Builds message lists for LLM calls with cache-aware structure."""

    def get_static_instructions(self) -> str:
        """Return the static system prompt text.

        Uses the user-configured prompt from settings if available,
        otherwise falls back to the built-in default.
        """
        custom = getattr(settings, "system_prompt", None)
        if custom and custom.strip():
            return custom.strip()
        return DEFAULT_SYSTEM_PROMPT

    def format_rag_context(
        self,
        retrieval_result: Optional[RetrievalResult],
        edition: Optional[str] = None,
    ) -> str:
        """Format retrieval results into labeled RAG context sections.

        Returns a string with authoritative and example sections,
        or empty string if no results.
        """
        if not retrieval_result or retrieval_result.is_empty:
            return ""

        sections = []

        # Edition context
        if edition:
            sections.append(
                f"The user is working with the **{edition}** edition. "
                f"Provide syntax and examples matching this edition."
            )

        # Authoritative section
        auth_section = _format_chunk_section(
            retrieval_result.authoritative,
            "Syntax rules and engine behavior (authoritative - trust these for correctness)",
        )
        if auth_section:
            sections.append(auth_section)

        # Examples section
        ex_section = _format_chunk_section(
            retrieval_result.examples,
            "Implementation examples (use these as patterns, but follow the rules above)",
        )
        if ex_section:
            sections.append(ex_section)

        return "\n\n".join(sections)

    def build_messages(
        self,
        query: str,
        retrieval_result: Optional[RetrievalResult] = None,
        conversation_history: Optional[list[dict]] = None,
        edition: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> list[dict]:
        """Build the complete message list for an LLM call.

        Returns raw dicts (not LangChain Message objects) so that
        cache_control can be attached for Anthropic.  The LLM client
        passes these directly to the provider.

        Args:
            query: Current user question.
            retrieval_result: Output from the retriever (may be None).
            conversation_history: Previous messages as dicts with
                'role' and 'content' keys (from session DB).
            edition: Active edition for context.
            provider: LLM provider name (affects cache_control).

        Returns:
            List of message dicts ready for the LLM client.
        """
        messages = []

        # System message (two content blocks)
        static_text = self.get_static_instructions()
        rag_context = self.format_rag_context(retrieval_result, edition)

        system_content = self._build_system_content(
            static_text=static_text,
            rag_context=rag_context,
            provider=provider or settings.default_llm_provider,
        )
        messages.append({"role": "system", "content": system_content})

        # Conversation history
        if conversation_history:
            for msg in conversation_history:
                messages.append(
                    {
                        "role": msg["role"],
                        "content": msg["content"],
                    }
                )

        # Current user query
        messages.append({"role": "user", "content": query})

        return messages

    def _build_system_content(
        self,
        static_text: str,
        rag_context: str,
        provider: str,
    ) -> list[dict] | str:
        """Build system message content, with cache_control for Anthropic.

        For Anthropic: returns a list of content blocks so the static
        portion can be cached separately from the dynamic RAG context.

        For other providers: returns a plain string (they don't support
        content blocks in system messages).
        """
        if provider == "anthropic":
            blocks = [
                {
                    "type": "text",
                    "text": static_text,
                    "cache_control": {"type": "ephemeral"},
                },
            ]

            if rag_context:
                blocks.append(
                    {
                        "type": "text",
                        "text": rag_context,
                    }
                )

            return blocks

        # OpenAI / Ollama: plain string
        if rag_context:
            return f"{static_text}\n\n{rag_context}"
        return static_text


# * Global instance
prompt_builder = PromptBuilder()
