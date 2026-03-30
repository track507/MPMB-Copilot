from app.main import app
import pytest
from fastapi.testclient import TestClient

client = TestClient(app)


def ping():
    """Test simple ping endpoint"""
    print("=" * 40)
    print("Running ping test")
    print("=" * 40)
    response = client.get("/api/ping")
    assert response.status_code == 200
    data = response.json()
    print(f"data: {data}")
    assert "ping" in data
    assert data["ping"] == "pong"
    assert "timestamp" in data


def health_check():
    print("=" * 40)
    print("Running health check test")
    print("=" * 40)
    """Test detailed health check endpoint"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    print(f"data: {data}")

    # Check required fields
    assert "status" in data
    assert "environment" in data
    assert "version" in data
    assert "timestamp" in data
    assert "services" in data
    # Check services
    services = data["services"]
    assert "qdrant" in services
    assert "llm_provider" in services
    assert "embedding_model" in services
    # Each service should have status and message
    for service_name, service_info in services.items():
        assert "status" in service_info
        assert "message" in service_info


def test_root_endpoint():
    print("=" * 40)
    print("Running root endpoint test")
    print("=" * 40)
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    print(f"data: {data}")
    assert "name" in data
    assert "version" in data
    assert "status" in data
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_health_response_model():
    print("=" * 40)
    print("Running health response model test")
    print("=" * 40)
    """Test health response contains all expected fields"""
    from app.api.health import health_check

    response = await health_check()
    print(f"response: {response}")

    assert response.status in ["healthy", "degraded", "unhealthy"]
    assert response.environment in ["development", "production", "testing"]
    assert response.version == "0.1.0"
    assert response.timestamp is not None
    assert isinstance(response.services, dict)
