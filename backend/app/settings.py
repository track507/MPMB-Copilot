"""Hot-reloadable behavioral settings.

Manages settings that affect per-query behavior (LLM params, retrieval
tuning, intent detection) and can change at runtime without restarting
the server.

Reads from a JSON file on disk.  Falls back to infrastructure defaults
from `app.config.config` when the file is missing or a field is absent.

The frontend writes settings via `PATCH /api/settings`; the backend
persists them here and applies them on the next query.

Usage:
    from app.settings import settings

    # Read (always current):
    model = settings.default_model
    budgets = settings.tier_budgets

    # Hot-reload from disk (e.g. after external edit):
    settings.reload()

    # Programmatic update (e.g. from API endpoint):
    settings.update(temperature=0.5, default_edition="2024")

    # Persist current state:
    settings.save()
"""

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.logger import get_logger

logger = get_logger(__name__)

# Project root resolved from this file: backend/app/settings.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Default tier budgets per intent.
# Keys are intent names, values set how many chunks to fetch from each tier.
_DEFAULT_TIER_BUDGETS: dict[str, dict[str, int]] = {
    "how_to": {"authoritative": 3, "examples": 5},
    "generate": {"authoritative": 2, "examples": 5},
    "debug": {"authoritative": 4, "examples": 2},
    "lookup": {"authoritative": 4, "examples": 2},
}


@dataclass
class Settings:
    """Behavioral settings that can change at runtime.

    Every field has a sensible default sourced from `config.py` values
    or hardcoded fallbacks.  The JSON file on disk stores only the fields
    the user has explicitly changed - missing keys use defaults.
    """

    # LLM behavior
    default_llm_provider: str = "anthropic"
    default_model: str = "claude-sonnet-4-6"
    temperature: float = 0.2
    max_tokens: int = 8000

    default_effort: str = "high"
    """
    Reasoning effort for the main model (low/medium/high/xhigh/max on Anthropic, minimal/low/medium/high on OpenAI)
    Applied only when the selected model supports it; ignored otherwise. 'high' is the provider default
    """

    # * Upload API caps (independent from tool_max_file_bytes: stored files may exceed a single tool read)
    upload_max_file_bytes: int = 52_428_800
    upload_max_files_per_scope: int = 200

    # Embedding selection (the model that builds and queries the vector index)
    # Dimension is derived from the catalog via embedding_dim(), not stored here
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Cheap model aliases for non-generation tasks (titles, future routing)
    # Per provider so switching default_llm_provider keeps a sensible cheap model
    anthropic_cheap_model: str = "claude-haiku-4-5"
    openai_cheap_model: str = "gpt-5.4-mini"
    ollama_cheap_model: str = ""  # ? empty falls back to default_model

    # RAG tuning
    default_edition: str = "2014"
    top_k_results: int = 8
    similarity_threshold: float = 0.5
    context_window_size: int = 8000

    # Retrieval
    retrieval_mode: str = "dual"
    """'single' = one hybrid search, split after.
    'dual'   = two searches (authoritative + examples).
    'auto'   = dual when intent is detected, single otherwise."""

    intent_method: str = "hybrid"
    """'embedding' = centroid classification only.
    'rule'      = regex/symbol patterns only.
    'hybrid'    = embedding + symbol boosts (recommended)."""

    intent_confidence_threshold: float = 0.35
    """Minimum cosine similarity to accept an intent classification."""

    intent_confidence_margin: float = 0.05
    """If gap between top-2 intents is below this, blend both profiles."""

    tier_budgets: dict[str, dict[str, int]] = field(
        default_factory=lambda: dict(_DEFAULT_TIER_BUDGETS),
    )

    # Reranking (cross-encoder over hybrid candidates, applied per tier before the budget cut)
    rerank_enabled: bool = True
    """On by default: run_eval matrix"""

    rerank_provider: str = "fastembed"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"

    rerank_candidate_k: int = 24
    """Candidates fetched + scored per tier before the budget cut. Bounds rerank latency."""

    # Global inference model, default CPU
    inference_device: str = "cpu"
    """
    Device preference for locally-run ONNX models (embedding, reranking)
    'gpu' means use the GPU where applicable: cloud providers ignore it and a failed GPU load falls back to CPU per model
    'cpu' is the safe default
    """

    # Auth sessions
    session_lifetime_days: int = 30
    """Absolute auth-session lifetime; the cookie max-age matches."""

    session_idle_days: int = 7
    """Sliding idle timeout; a session unused this long expires early."""

    # Tool use
    enable_tool_use: bool = False
    """Allow the LLM to call MPMB source verification tools."""

    max_tool_calls: int = 12
    """Soft budget on tool calls per chat turn. Over budget, tools return a stop notice
    so the model answers with what it has. 0 = no soft cap (a hard net of 50 model
    requests per turn still applies, handled gracefully)."""

    source_catalog_path: Optional[str] = None
    """Override path to mpmb-analysis.json. None → resolution falls through to
    config/env, then to ./scripts/analyze/reports/mpmb-analysis.json."""

    source_catalog_enabled: bool = True
    """Master switch. False → service stays in MISSING state regardless of file."""

    inject_catalog_context: bool = True
    """When True, prompt builder renders catalog-derived registry/Add blocks
    into the system prompt and per-query hints into the user prompt."""

    # ! tool_search_limit is deprecated, retrieval now handles enumeration. Field kept for settings JSON compat.
    tool_search_limit: int = 5
    """Deprecated legacy field. Kept for settings JSON compat."""

    tool_grep_max_matches: int = 50
    """Max match rows returned by mpmb_grep before truncation tag."""

    tool_max_file_bytes: int = 1_048_576
    """Reject reads when the resolved file is larger than this (bytes)."""

    tool_read_max_lines: int = 2000
    """Hard cap on lines returned by mpmb_read in a single call."""

    tool_grep_pattern_max_len: int = 500
    """Reject grep patterns longer than this many characters."""

    tool_grep_file_timeout_sec: float = 1.0
    """Per-file regex timeout for mpmb_grep (approximate; enforced via elapsed-time check)."""

    # Anthropic prompt caching (Anthropic only)
    anthropic_cache_instructions: bool = True
    """Cache the static system instructions block (5m TTL)."""

    anthropic_cache_messages: bool = True
    """Cache the latest message in conversation history."""

    anthropic_cache_tool_definitions: bool = True
    """Cache the tool definitions block. Covers the toolset even when instruction caching is disabled"""

    # Extended thinking (Anthropic only)
    enable_extended_thinking: bool = False
    """Enable adaptive thinking (the model decides reasoning depth)
    On newer models depth is governed by `default_effort`; the legacy numeric thinking budget is no longer used"""

    # System prompt
    system_prompt: Optional[str] = None
    """Custom system prompt override.  When set, replaces the built-in
    default in prompts.py.  Editable from the frontend settings screen."""

    # Internal bookkeeping (not serialized)
    _file_path: Optional[Path] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # Lifecycle
    @classmethod
    def from_config(cls, config_module: Any = None) -> "Settings":
        """Create a Settings instance using config.py defaults.

        Call once at startup.  Attempts to load the JSON file afterward.
        """
        if config_module is None:
            from app.config import config as config_module

        instance = cls(
            default_llm_provider=getattr(config_module, "default_llm_provider", cls.default_llm_provider),
            default_model=getattr(config_module, "default_model", cls.default_model),
            temperature=getattr(config_module, "temperature", cls.temperature),
            max_tokens=getattr(config_module, "max_tokens", cls.max_tokens),
            embedding_provider=getattr(config_module, "embedding_provider", cls.embedding_provider),
            embedding_model=getattr(config_module, "embedding_model", cls.embedding_model),
            default_edition=getattr(config_module, "default_edition", cls.default_edition),
            top_k_results=getattr(config_module, "top_k_results", cls.top_k_results),
            similarity_threshold=getattr(config_module, "similarity_threshold", cls.similarity_threshold),
            context_window_size=getattr(config_module, "context_window_size", cls.context_window_size),
            enable_tool_use=getattr(config_module, "enable_tool_use", cls.enable_tool_use),
            max_tool_calls=getattr(config_module, "max_tool_calls", cls.max_tool_calls),
            enable_extended_thinking=getattr(config_module, "enable_extended_thinking", cls.enable_extended_thinking),
            tool_search_limit=getattr(config_module, "tool_search_limit", cls.tool_search_limit),
            system_prompt=getattr(config_module, "system_prompt", cls.system_prompt),
            source_catalog_path=getattr(config_module, "source_catalog_path", cls.source_catalog_path),
            source_catalog_enabled=getattr(config_module, "source_catalog_enabled", cls.source_catalog_enabled),
            inject_catalog_context=getattr(config_module, "inject_catalog_context", cls.inject_catalog_context),
        )

        # Resolve JSON file path from the repo root, not the current process cwd.
        settings_file = getattr(config_module, "settings_file", None)
        if settings_file is None:
            settings_file = Path(getattr(config_module, "data_dir", "./data")) / "settings.json"

        settings_path = Path(settings_file)
        if not settings_path.is_absolute():
            settings_path = _REPO_ROOT / settings_path
        instance._file_path = settings_path

        # Overlay persisted user settings (if file exists)
        instance.reload()

        return instance

    # Read / write
    def reload(self) -> bool:
        """Re-read the JSON file and merge into current state.

        Only fields present in the file are overwritten; everything else
        keeps its current value.  Returns True if file was loaded.
        """
        if not self._file_path or not self._file_path.exists():
            return False

        try:
            with self._lock:
                raw = json.loads(self._file_path.read_text(encoding="utf-8"))

            if not isinstance(raw, dict):
                logger.warning(f"Settings file is not a JSON object: {self._file_path}")
                return False

            self._apply(raw)
            logger.info(f"Settings loaded from {self._file_path} ({len(raw)} keys)")
            return True

        except Exception as e:
            logger.warning(f"Failed to load settings from {self._file_path}: {e}")
            return False

    def save(self) -> bool:
        """Persist current state to the JSON file.

        Creates parent directories if needed.  Returns True on success.
        """
        if not self._file_path:
            return False

        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

            data = self.to_dict()

            with self._lock:
                self._file_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            logger.info(f"Settings saved to {self._file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save settings to {self._file_path}: {e}")
            return False

    def update(self, **kwargs: Any) -> None:
        """Apply a partial update and persist to disk.

        Only known fields are accepted; unknown keys are silently ignored.

        Example:
            settings.update(temperature=0.5, default_edition="2024")
        """
        self._apply(kwargs)
        self.save()

    # Serialization
    def to_dict(self) -> dict[str, Any]:
        """Return all user-facing settings as a plain dict.

        Excludes internal fields (prefixed with `_`).
        """
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values() if not f.name.startswith("_")}

    def embedding_dim(self) -> int:
        """Dimension of the selected embedding model, sourced from the catalog"""
        from app.core.embedding_catalog import dimension_for

        return dimension_for(self.embedding_provider, self.embedding_model)

    def cheap_model_for(self, provider: Optional[str] = None) -> str:
        """Resolve the cheap-model alias for the given (or default) provider."""
        provider = provider or self.default_llm_provider
        if provider == "anthropic":
            return self.anthropic_cheap_model
        if provider == "openai":
            return self.openai_cheap_model
        if provider == "ollama":
            return self.ollama_cheap_model or self.default_model
        return self.default_model

    def get_tier_budget(self, intent: str) -> dict[str, int]:
        """Return the tier budget for a given intent.

        Falls back to how_to budget if the intent is unknown.
        """
        return self.tier_budgets.get(
            intent,
            self.tier_budgets.get(
                "how_to",
                {
                    "authoritative": 3,
                    "examples": 5,
                },
            ),
        )

    # Internal helpers
    def _apply(self, data: dict[str, Any]) -> None:
        """Merge a dict into the current settings (known fields only)."""
        known_fields = {f.name for f in self.__dataclass_fields__.values() if not f.name.startswith("_")}

        for key, value in data.items():
            if key in known_fields:
                setattr(self, key, value)


def _create_settings() -> Settings:
    """Build the global settings instance.

    Tries to load from config.py; if that module isn't available yet
    (e.g. during isolated testing), uses pure defaults.
    """
    try:
        return Settings.from_config()
    except Exception:
        logger.info("Config module not available; using default settings")
        return Settings()


# * Global instance
settings = _create_settings()
