"""Tests for OCR service implementations."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from app.services.mistral_ocr import MistralOCRService
from app.services.ocr_base import OCRResult
from app.utils.exceptions import (
    OCRExtractionError,
    OCRTimeoutError,
    InvalidDocumentError,
    APIClientError,
)


class TestMistralOCRService:
    """Test suite for MistralOCRService.

    Tests the public interface of the Mistral OCR service implementation,
    focusing on business logic and behavior rather than implementation details.
    """

    @pytest.fixture
    def ocr_service(self) -> MistralOCRService:
        """Create MistralOCRService instance for testing.

        Returns:
            MistralOCRService: Configured service instance
        """
        return MistralOCRService(
            api_key="test-api-key",
            api_url="https://api.mistral.ai/v1/chat/completions",
            model="pixtral-12b-2409",
            timeout=60,
            max_retries=3,
            retry_delay=1,
        )

    def test_get_service_name(self, ocr_service: MistralOCRService) -> None:
        """Test that service returns correct name.

        Args:
            ocr_service: OCR service fixture
        """
        assert ocr_service.get_service_name() == "Mistral OCR"

    @pytest.mark.asyncio
    async def test_extract_text_from_url_success(
        self, ocr_service: MistralOCRService, sample_pdf_url: str, sample_pdf_content: bytes
    ) -> None:
        """Test successful text extraction from URL.

        Args:
            ocr_service: OCR service fixture
            sample_pdf_url: Sample PDF URL fixture
            sample_pdf_content: Sample PDF content fixture
        """
        # Mock httpx responses
        mock_download_response = Mock()
        mock_download_response.content = sample_pdf_content
        mock_download_response.headers = {"content-type": "application/pdf"}
        mock_download_response.raise_for_status = Mock()

        mock_api_response = Mock()
        mock_api_response.json.return_value = {
            "pages": [{"markdown": "Extracted text content from document"}]
        }
        mock_api_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_download_response
            mock_client.post.return_value = mock_api_response
            mock_client_class.return_value = mock_client

            # Execute
            result = await ocr_service.extract_text_from_url(sample_pdf_url)

            # Assert
            assert isinstance(result, OCRResult)
            assert result.text == "Extracted text content from document"
            assert result.confidence == 0.95
            assert result.metadata["service"] == "Mistral OCR"
            assert result.metadata["model"] == "pixtral-12b-2409"
            assert "processing_time_seconds" in result.metadata
            assert result.metadata["document_url"] == sample_pdf_url

    @pytest.mark.asyncio
    async def test_extract_text_from_url_download_fails(
        self, ocr_service: MistralOCRService, sample_pdf_url: str
    ) -> None:
        """Test extraction fails when document download fails.

        Args:
            ocr_service: OCR service fixture
            sample_pdf_url: Sample PDF URL fixture
        """
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Simulate HTTP 404 error
            mock_response = Mock()
            mock_response.status_code = 404
            mock_client.get.side_effect = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=mock_response
            )
            mock_client_class.return_value = mock_client

            # Execute and assert
            with pytest.raises(InvalidDocumentError) as exc_info:
                await ocr_service.extract_text_from_url(sample_pdf_url)

            assert "Failed to download document" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_text_from_url_api_timeout(
        self, ocr_service: MistralOCRService, sample_pdf_url: str, sample_pdf_content: bytes
    ) -> None:
        """Test extraction fails when API times out.

        Args:
            ocr_service: OCR service fixture
            sample_pdf_url: Sample PDF URL fixture
            sample_pdf_content: Sample PDF content fixture
        """
        mock_download_response = Mock()
        mock_download_response.content = sample_pdf_content
        mock_download_response.headers = {"content-type": "application/pdf"}
        mock_download_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_download_response
            mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
            mock_client_class.return_value = mock_client

            # Execute and assert
            with pytest.raises(OCRTimeoutError) as exc_info:
                await ocr_service.extract_text_from_url(sample_pdf_url)

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_extract_text_from_url_api_error(
        self, ocr_service: MistralOCRService, sample_pdf_url: str, sample_pdf_content: bytes
    ) -> None:
        """Test extraction fails when API returns error.

        Args:
            ocr_service: OCR service fixture
            sample_pdf_url: Sample PDF URL fixture
            sample_pdf_content: Sample PDF content fixture
        """
        mock_download_response = Mock()
        mock_download_response.content = sample_pdf_content
        mock_download_response.headers = {"content-type": "application/pdf"}
        mock_download_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_download_response

            # Simulate API error on all retry attempts
            mock_response = Mock()
            mock_response.status_code = 500
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "Internal Server Error", request=Mock(), response=mock_response
            )
            mock_client_class.return_value = mock_client

            # Execute and assert
            with pytest.raises(APIClientError) as exc_info:
                await ocr_service.extract_text_from_url(sample_pdf_url)

            assert "Mistral OCR API" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_text_from_url_retry_logic(
        self, ocr_service: MistralOCRService, sample_pdf_url: str, sample_pdf_content: bytes
    ) -> None:
        """Test that service retries on transient failures.

        Args:
            ocr_service: OCR service fixture
            sample_pdf_url: Sample PDF URL fixture
            sample_pdf_content: Sample PDF content fixture
        """
        mock_download_response = Mock()
        mock_download_response.content = sample_pdf_content
        mock_download_response.headers = {"content-type": "application/pdf"}
        mock_download_response.raise_for_status = Mock()

        mock_api_response = Mock()
        mock_api_response.json.return_value = {
            "pages": [{"markdown": "Success after retry"}]
        }
        mock_api_response.raise_for_status = Mock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_download_response

            # First call fails, second succeeds
            mock_response = Mock()
            mock_response.status_code = 503
            mock_client.post.side_effect = [
                httpx.HTTPStatusError(
                    "Service Unavailable", request=Mock(), response=mock_response
                ),
                mock_api_response,
            ]
            mock_client_class.return_value = mock_client

            # Execute
            result = await ocr_service.extract_text_from_url(sample_pdf_url)

            # Assert - should succeed after retry
            assert result.text == "Success after retry"
            assert mock_client.post.call_count == 2


class TestOCRResult:
    """Test suite for OCRResult class."""

    def test_ocr_result_initialization(self) -> None:
        """Test OCRResult initialization with required fields."""
        result = OCRResult(
            text="Sample text",
            confidence=0.95,
        )

        assert result.text == "Sample text"
        assert result.confidence == 0.95
        assert result.metadata == {}
        assert result.layout is None

    def test_ocr_result_with_metadata(self) -> None:
        """Test OCRResult initialization with metadata."""
        metadata = {"service": "Test OCR", "processing_time": 1.5}
        result = OCRResult(
            text="Sample text",
            confidence=0.95,
            metadata=metadata,
        )

        assert result.metadata == metadata

    def test_ocr_result_to_dict(self) -> None:
        """Test OCRResult conversion to dictionary."""
        result = OCRResult(
            text="Sample text",
            confidence=0.95,
            metadata={"service": "Test OCR"},
        )

        result_dict = result.to_dict()

        assert result_dict["text"] == "Sample text"
        assert result_dict["confidence"] == 0.95
        assert result_dict["metadata"]["service"] == "Test OCR"
        assert "layout" not in result_dict

    def test_ocr_result_to_dict_with_layout(self) -> None:
        """Test OCRResult conversion to dictionary with layout."""
        layout = {"page": 1, "boxes": []}
        result = OCRResult(
            text="Sample text",
            confidence=0.95,
            layout=layout,
        )

        result_dict = result.to_dict()

        assert result_dict["layout"] == layout

