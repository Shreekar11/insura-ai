"""Tests for API endpoints."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
)
from app.services.processed.services.ocr.ocr_service import OCRService


class TestOCREndpoints:
    """Test suite for OCR API endpoints.

    Tests the public API interface, focusing on request/response behavior
    and error handling.
    """
    def test_extract_ocr_invalid_url(self, test_client: TestClient) -> None:
        """Test OCR extraction with invalid URL.

        Args:
            test_client: FastAPI test client fixture
        """
        response = test_client.post(
            "/api/v1/ocr/extract",
            json={"pdf_url": "not-a-valid-url"},
        )

        # Assert - should fail validation
        assert response.status_code == 422

    def test_extract_ocr_missing_url(self, test_client: TestClient) -> None:
        """Test OCR extraction with missing URL.

        Args:
            test_client: FastAPI test client fixture
        """
        response = test_client.post(
            "/api/v1/ocr/extract",
            json={},
        )

        # Assert - should fail validation
        assert response.status_code == 422

    def test_extract_ocr_invalid_document_error(
        self, test_client: TestClient, sample_pdf_url: str
    ) -> None:
        """Test OCR extraction with invalid document.

        Args:
            test_client: FastAPI test client fixture
            sample_pdf_url: Sample PDF URL fixture
        """
        mock_service = AsyncMock()
        mock_service.extract_text_from_url.side_effect = InvalidDocumentError(
            "Document not found"
        )
        app.dependency_overrides[OCRService] = lambda: mock_service

        # Execute
        response = test_client.post(
            "/api/v1/ocr/extract",
            json={"pdf_url": sample_pdf_url},
        )

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "InvalidDocumentError"

    def test_extract_ocr_timeout_error(
        self, test_client: TestClient, sample_pdf_url: str
    ) -> None:
        """Test OCR extraction with timeout.

        Args:
            test_client: FastAPI test client fixture
            sample_pdf_url: Sample PDF URL fixture
        """
        mock_service = AsyncMock()
        mock_service.extract_text_from_url.side_effect = OCRTimeoutError(
            "Processing timed out"
        )
        app.dependency_overrides[OCRService] = lambda: mock_service

        # Execute
        response = test_client.post(
            "/api/v1/ocr/extract",
            json={"pdf_url": sample_pdf_url},
        )

        # Assert
        assert response.status_code == 408
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "OCRTimeoutError"

    def test_extract_ocr_extraction_error(
        self, test_client: TestClient, sample_pdf_url: str
    ) -> None:
        """Test OCR extraction with extraction error.

        Args:
            test_client: FastAPI test client fixture
            sample_pdf_url: Sample PDF URL fixture
        """
        mock_service = AsyncMock()
        mock_service.extract_text_from_url.side_effect = OCRExtractionError(
            "Extraction failed"
        )
        app.dependency_overrides[OCRService] = lambda: mock_service

        # Execute
        response = test_client.post(
            "/api/v1/ocr/extract",
            json={"pdf_url": sample_pdf_url},
        )

        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "OCRExtractionError"


class TestHealthEndpoint:
    """Test suite for health check endpoint."""

    def test_health_check(self, test_client: TestClient) -> None:
        """Test health check endpoint returns healthy status.

        Args:
            test_client: FastAPI test client fixture
        """
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "service" in data


class TestRootEndpoint:
    """Test suite for root endpoint."""

    def test_root_endpoint(self, test_client: TestClient) -> None:
        """Test root endpoint returns API information.

        Args:
            test_client: FastAPI test client fixture
        """
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "docs" in data
        assert "health" in data

