"""Health check API models

This module defines Pydantic models for the /health endpoint, which provides
system status monitoring for MPMB-Copilot's various service dependencies.

The health check endpoint allows monitoring systems and load balancers to verify
that the application and its dependencies (PostgreSQL, Qdrant, LLM providers) are
operational.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class ServiceStatus(BaseModel):
	"""Status information for an individual service dependency.

	Represents the health status of a single external service or component
	that MPMB-Copilot depends on (database, vector store, LLM provider, etc.).

	Attributes:
		status: Service health status. Standard values:
			- "healthy": Service is operational
			- "degraded": Service is functional but experiencing issues
			- "unhealthy": Service is not operational
			- "unknown": Unable to determine service status
		message: Optional human-readable status message providing additional
			context about the service state (e.g., error messages, latency info)

	Example:
		>>> status = ServiceStatus(
		...     status="healthy",
		...     message="Connected to PostgreSQL 15.3"
		... )
		>>>
		>>> error_status = ServiceStatus(
		...     status="unhealthy",
		...     message="Connection timeout after 5000ms"
		... )
	"""
	status: str = Field(..., description="Service health status (healthy/degraded/unhealthy/unknown)")
	message: Optional[str] = Field(None, description="Optional status message or error details")

class HealthResponse(BaseModel):
	"""Health check response model from the /health endpoint.

	Provides comprehensive system health information including overall status,
	environment details, version info, and individual service statuses for all
	dependencies.

	This response is used by:
	- Load balancers for health checks
	- Monitoring systems (Prometheus, Datadog, etc.)
	- Deployment pipelines for readiness checks
	- Debugging and troubleshooting

	Attributes:
		status: Overall system health status. Values:
			- "healthy": All services operational
			- "degraded": Some non-critical services have issues
			- "unhealthy": Critical services are down
		environment: Deployment environment (e.g., "development", "staging", "production")
		version: Application version (semver format, e.g., "1.2.3")
		timestamp: Current server time in UTC when health check was performed
		services: Dictionary mapping service names to their status details.
			Standard service keys:
			- "database": PostgreSQL connection status
			- "vector_db": Qdrant vector database status
			- "llm_anthropic": Anthropic API status (if configured)
			- "llm_openai": OpenAI API status (if configured)
			- "llm_ollama": Ollama local LLM status (if configured)
			- "storage": File storage system status
			Each value is a dict with "status" and optional "message" keys.

	Example:
		>>> response = HealthResponse(
		...     status="healthy",
		...     environment="production",
		...     version="1.0.0",
		...     timestamp=datetime.now(timezone.utc),
		...     services={
		...         "database": {"status": "healthy", "message": "PostgreSQL 15.3"},
		...         "vector_db": {"status": "healthy", "message": "Qdrant 1.7.0"},
		...         "llm_anthropic": {"status": "healthy", "message": "API key valid"}
		...     }
		... )
		>>>
		>>> # Degraded example
		>>> degraded = HealthResponse(
		...     status="degraded",
		...     environment="production",
		...     version="1.0.0",
		...     timestamp=datetime.now(timezone.utc),
		...     services={
		...         "database": {"status": "healthy"},
		...         "vector_db": {"status": "degraded", "message": "High latency: 850ms"},
		...         "llm_anthropic": {"status": "healthy"}
		...     }
		... )

	Note:
		The services dictionary structure is flexible to accommodate different
		deployment configurations. Not all services need to be present in every
		environment (e.g., Ollama may only be in development).
	"""
	status: str = Field(..., description="Overall system health (healthy/degraded/unhealthy)")
	environment: str = Field(..., description="Deployment environment name")
	version: str = Field(..., description="Application version (semver)")
	timestamp: datetime = Field(..., description="Health check timestamp (UTC)")
	services: dict[str, dict[str, str]] = Field(
		...,
		description="Service-specific health statuses keyed by service name"
	)
