"""Pytest configuration and fixtures"""

import os
import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"

from app.main import app
from app.config import settings


@pytest.fixture
def client():
    """FastAPI test client fixture"""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_settings():
    """Settings fixture for tests"""
    return settings


@pytest.fixture
def sample_code_chunk():
    """Sample code chunk for testing"""
    return """
var SpellsList = {
	"magic_missile": {
		name: "Magic Missile",
		source: ["P", 257],
		level: 1,
		school: "Evoc",
		time: "1 a",
		range: "120 ft",
		components: "V,S",
		duration: "Instantaneous",
		description: "3 missiles hit creatures for 1d4+1 force damage each",
		descriptionFull: "You create three glowing darts of magical force..."
	}
};
"""


@pytest.fixture
def sample_query():
    """Sample user query for testing"""
    return "How do I add a new spell to SpellsList?"


@pytest.fixture
def sample_embedding():
    """Sample embedding vector for testing"""
    return [0.1] * 384  # All-MiniLM-L6-v2 dimension
