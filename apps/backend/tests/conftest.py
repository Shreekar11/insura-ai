"""Pytest configuration and shared fixtures."""

import os
import pytest
from unittest.mock import Mock, AsyncMock

# Set required environment variables for testing BEFORE importing app
os.environ.setdefault("MISTRAL_API_KEY", "test-mistral-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-supabase-key")

from fastapi.testclient import TestClient

from app.main import app

@pytest.fixture
def test_client() -> TestClient:
    """Create FastAPI test client.

    Returns:
        TestClient: FastAPI test client instance
    """
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    """Ensure FastAPI dependency overrides are reset between tests."""
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}

@pytest.fixture
def sample_pdf_url() -> str:
    """Sample PDF URL for testing.

    Returns:
        str: Sample PDF URL
    """
    return "https://example.com/test-document.pdf"


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Sample PDF content for testing.

    Returns:
        bytes: Sample PDF content
    """
    # Minimal valid PDF header
    return b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"


@pytest.fixture
def mock_httpx_client() -> Mock:
    """Create mock httpx client.

    Returns:
        Mock: Mocked httpx client
    """
    client = Mock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client

