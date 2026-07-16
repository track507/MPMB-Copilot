"""Configuration management using pydantic-settings

Single source of truth for all application configuration.
Import `config` from this module anywhere in the app.
"""

import json
from pathlib import Path
from typing import Annotated, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# * Repo root resolved from this file: backend/app/config.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Config(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Settings
    app_name: str = "MPMB Copilot Backend"
    environment: Literal["development", "production", "testing"] = "development"
    log_level: str = "INFO"
    debug: bool = Field(default=False, description="Enable debug mode")

    # Auth / exposure
    # ! bind_host must mirror the launcher's --host so fail-safe exposure logic is honest
    bind_host: str = "127.0.0.1"
    cookie_secure: Literal["auto", "always", "never"] = "auto"
    # ! Env-only dev escape hatch; honored only when bind_host is loopback
    auth_disabled: bool = False

    # API Settings
    api_prefix: str = "/api"
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5000",
            "http://localhost:5001",
        ]
    )

    # LLM Provider Settings
    default_llm_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    default_model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000
    temperature: float = 0.2
    enable_tool_use: bool = False
    max_tool_calls: int = 0
    enable_extended_thinking: bool = False

    # API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ollama_host: str = "http://localhost:11434"

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "mpmb_user"
    postgres_password: str = "mpmb_password"
    postgres_db: str = "mpmb_copilot"
    database_url: Optional[str] = None

    @property
    def resolved_database_url(self) -> str:
        """Return DATABASE_URL if set, otherwise build from parts."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Vector Store
    # Which store implementation to use: "qdrant" (default), future: "weaviate", "pgvector"
    vector_store: Literal["qdrant"] = "qdrant"

    # Qdrant-specific settings (used when vector_store=qdrant)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "mpmb_code"
    qdrant_timeout: int = 30

    # Embedding Settings
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    # ! Cap ONNX threads during embedding so indexing does not saturate the machine (0 = auto: half the cores)
    embedding_threads: int = 0

    @property
    def resolved_embedding_threads(self) -> int:
        import os

        if self.embedding_threads > 0:
            return self.embedding_threads
        return max(1, (os.cpu_count() or 4) // 2)

    # RAG Parameters
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k_results: int = 8
    similarity_threshold: float = 0.5
    context_window_size: int = 8000
    default_edition: Literal["2014", "2024"] = "2014"

    # File Paths
    # All paths are strings so they load cleanly from .env.
    # Use the @property accessors for resolved Path objects.

    # Base data directory
    data_dir: str = "./data"

    # Source repositories
    mpmb_source_dir: str = "./data/mpmb_source"
    mpmb_source_2024_dir: str = "./data/mpmb_source_2024"
    imports_source_dir: str = "./data/imports_source"
    source_catalog_path: Optional[str] = Field(
        default=None,
        validation_alias="MPMB_CATALOG_PATH",
    )

    # Additional user-provided source directories (comma-separated)
    user_source_dirs: str = ""

    # Chunker output
    chunked_output_dir: str = "./data/chunked_output"

    # Other data directories
    adobe_docs_dir: str = "./data/adobe_docs"
    index_cache_dir: str = "./data/index_cache"
    upload_dir: str = "./data/uploads"

    # ! FastEmbed model cache: never the OS temp dir (Windows purges it, silently breaking retrieval)
    fastembed_cache_dir: str = "./data/models/fastembed"

    # Source Repository URLs (used by source acquisition scripts)
    mpmb_repo_url: str = "https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git"
    mpmb_repo_2024_url: str = "https://github.com/morepurplemorebetter/2024_MPMBs-Character-Record-Sheet.git"
    mpmb_repo_branch_2014: str = "master"
    mpmb_repo_branch_2024: str = "main"
    imports_repo_url: str = "https://github.com/safety-orange/Imports-for-MPMB-s-Character-Sheet.git"

    # Static validator (transport 1: per-call node subprocess; see the validator spec)
    validator_node_bin: str = "node"
    validator_script_path: str = "./scripts/validate/src/validate.mjs"
    validator_timeout_sec: float = 10.0
    validator_max_concurrency: int = 4

    # Computed Properties

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_value(cls, value: object) -> object:
        """Accept common environment-style debug values in addition to booleans."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"debug", "dev", "development"}:
                return True
            if normalized in {"release", "prod", "production"}:
                return False
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def normalize_allowed_origins(cls, value: object) -> object:
        """Accept ALLOWED_ORIGINS as either JSON or comma-separated text."""
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []

            if normalized.startswith("["):
                try:
                    decoded = json.loads(normalized)
                except json.JSONDecodeError:
                    pass
                else:
                    if isinstance(decoded, list):
                        return [str(item).strip() for item in decoded if str(item).strip()]

            return [origin.strip() for origin in normalized.split(",") if origin.strip()]

        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]

        return value

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def chunked_output_path(self) -> Path:
        return Path(self.chunked_output_dir)

    @property
    def fastembed_cache_path(self) -> Path:
        # ? Anchored to the repo root so uvicorn (repo cwd) and the evals scripts (backend cwd) share one cache
        path = Path(self.fastembed_cache_dir)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def user_source_paths(self) -> list[Path]:
        if not self.user_source_dirs:
            return []
        return [Path(d.strip()) for d in self.user_source_dirs.split(",") if d.strip()]

    @property
    def validator_script(self) -> Path:
        # ? Anchored to the repo root like fastembed_cache_path (cwd differs between uvicorn and scripts)
        path = Path(self.validator_script_path)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path

    @property
    def source_configs(self) -> list[dict]:
        """Build the list of source configurations for chunking/indexing.

        Each dict has: key, path, edition, repo, description.
        Only includes directories that exist on disk.
        """
        configs = []

        mpmb_master = Path(self.mpmb_source_dir)
        if mpmb_master.exists():
            configs.append(
                {
                    "key": "mpmb_master",
                    "path": mpmb_master,
                    "edition": "2014",
                    "repo": "mpmb",
                    "description": "MPMB main repo (master/2014)",
                }
            )

        mpmb_2024 = Path(self.mpmb_source_2024_dir)
        if mpmb_2024.exists():
            configs.append(
                {
                    "key": "mpmb_2024",
                    "path": mpmb_2024,
                    "edition": "2024",
                    "repo": "mpmb",
                    "description": "MPMB 2024 repo (main)",
                }
            )

        imports = Path(self.imports_source_dir)
        if imports.exists():
            configs.append(
                {
                    "key": "imports",
                    "path": imports,
                    "edition": "auto",
                    "repo": "imports",
                    "description": "safety-orange Imports repo",
                }
            )

        for i, user_path in enumerate(self.user_source_paths):
            if user_path.exists():
                configs.append(
                    {
                        "key": f"user_{i}",
                        "path": user_path,
                        "edition": "unknown",
                        "repo": "user",
                        "description": f"User source: {user_path}",
                    }
                )

        return configs

    def get_llm_api_key(self, provider: Optional[str] = None) -> Optional[str]:
        provider = provider or self.default_llm_provider
        if provider == "anthropic":
            return self.anthropic_api_key
        elif provider == "openai":
            return self.openai_api_key
        return None


# Global config instance
config = Config()
