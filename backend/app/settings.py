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
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

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
    default_model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.2
    max_tokens: int = 4000

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

    # Extended thinking + tools
    enable_tool_use: bool = False
    max_tool_calls: int = 5
    enable_extended_thinking: bool = False
    thinking_budget_tokens: int = 4000

    # Internal bookkeeping (not serialized)
    _file_path: Optional[Path] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # * Lifecycle
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
            default_edition=getattr(config_module, "default_edition", cls.default_edition),
            top_k_results=getattr(config_module, "top_k_results", cls.top_k_results),
            similarity_threshold=getattr(config_module, "similarity_threshold", cls.similarity_threshold),
            context_window_size=getattr(config_module, "context_window_size", cls.context_window_size),
            enable_tool_use=getattr(config_module, "enable_tool_use", cls.enable_tool_use),
            max_tool_calls=getattr(config_module, "max_tool_calls", cls.max_tool_calls),
            enable_extended_thinking=getattr(config_module, "enable_extended_thinking", cls.enable_extended_thinking),
            thinking_budget_tokens=getattr(config_module, "thinking_budget_tokens", cls.thinking_budget_tokens),
        )

        # Resolve JSON file path
        settings_file = getattr(config_module, "settings_file", None) or "./data/settings.json"
        instance._file_path = Path(settings_file)

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
