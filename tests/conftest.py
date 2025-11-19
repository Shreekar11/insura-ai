"""Pytest configuration and shared fixtures."""

import pytest
from unittest.mock import Mock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.ocr.ocr_service import OCRService
from app.services.ocr_base import OCRResult


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
def mock_ocr_service() -> Mock:
    """Create mock OCR service.

    Returns:
        Mock: Mocked OCR service instance
    """
    service = Mock(spec=OCRService)
    service.get_service_name.return_value = "Mistral OCR"
    return service


@pytest.fixture
def sample_ocr_result() -> OCRResult:
    """Create sample OCR result for testing.

    Returns:
        OCRResult: Sample OCR result
    """
    return OCRResult(
        text="Policy Number: 12345ABC\nCoverage: Property Damage\nEffective Date: 2023-07-10",
        confidence=0.97,
        metadata={
            "service": "Mistral OCR",
            "model": "pixtral-12b-2409",
            "processing_time_seconds": 2.5,
        },
    )


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

