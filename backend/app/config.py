"""Configuration management using pydantic-settings

Single source of truth for all application configuration.
Import `settings` from this module anywhere in the app.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Settings
    app_name: str = "MPMB Copilot Backend"
    environment: Literal["development", "production", "testing"] = "development"
    log_level: str = "INFO"
    debug: bool = Field(default=False, description="Enable debug mode")

    # API Settings
    api_prefix: str = "/api"
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5000",
            "http://localhost:5001",
        ]
    )

    # LLM Provider Settings
    default_llm_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    default_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4000
    temperature: float = 0.2

    # API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ollama_host: str = "http://localhost:11434"

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

    # Additional user-provided source directories (comma-separated)
    user_source_dirs: str = ""

    # Chunker output
    chunked_output_dir: str = "./data/chunked_output"

    # Other data directories
    adobe_docs_dir: str = "./data/adobe_docs"
    index_cache_dir: str = "./data/index_cache"
    upload_dir: str = "./data/uploads"

    # Source Repository URLs (used by acquire_sources script)
    mpmb_repo_url: str = "https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git"
    mpmb_repo_branch_2014: str = "master"
    mpmb_repo_branch_2024: str = "dnd2024"
    imports_repo_url: str = "https://github.com/safety-orange/Imports-for-MPMB-s-Character-Sheet.git"

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
    def user_source_paths(self) -> list[Path]:
        if not self.user_source_dirs:
            return []
        return [Path(d.strip()) for d in self.user_source_dirs.split(",") if d.strip()]

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
                    "description": "MPMB main repo (dnd2024)",
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


# Global settings instance
settings = Settings()
