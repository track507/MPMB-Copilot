"""Configuration management using pydantic-settings"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional


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

	# Qdrant Vector Database
	qdrant_host: str = "localhost"
	qdrant_port: int = 6333
	qdrant_collection: str = "mpmb_code"
	qdrant_timeout: int = 30

	# Embedding Settings
	embedding_provider: str = "sentence-transformers"
	embedding_model: str = "all-MiniLM-L6-v2"
	embedding_dimension: int = 384

	# RAG Parameters
	chunk_size: int = 1000
	chunk_overlap: int = 200
	top_k_results: int = 5
	similarity_threshold: float = 0.7
	context_window_size: int = 8000

	# File Paths
	data_dir: str = "./data"
	mpmb_source_dir: str = "./data/mpmb_source"
	adobe_docs_dir: str = "./data/adobe_docs"
	index_cache_dir: str = "./data/index_cache"

	@property
	def is_development(self) -> bool:
		"""Check if running in development mode"""
		return self.environment == "development"

	@property
	def is_production(self) -> bool:
		"""Check if running in production mode"""
		return self.environment == "production"

	def get_llm_api_key(self, provider: Optional[str] = None) -> Optional[str]:
		"""Get API key for specified provider"""
		provider = provider or self.default_llm_provider
		if provider == "anthropic":
			return self.anthropic_api_key
		elif provider == "openai":
			return self.openai_api_key
		return None


# Global settings instance
settings = Settings()
