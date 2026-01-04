from typing import List, Dict, Any

from app.core.base_llm_client import BaseLLMClient
from app.models.page_data import PageData
from app.utils.exceptions import InvalidDocumentError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class OCRRepository(BaseLLMClient):
    """Repository for OCR-related external operations.
    
    Inherits from BaseLLMClient for standardized API interactions.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str,
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: int = 2,
    ):
        """Initialize OCR repository.

        Args:
            api_key: Mistral API key
            api_url: Mistral API endpoint URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
        """
        super().__init__(
            api_key=api_key,
            base_url=api_url,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

    async def download_document(self, document_url: str) -> bytes:
        """Download document from URL.
        
        Note: BaseLLMClient is optimized for JSON APIs. 
        For binary downloads, we might still use httpx directly or extend BaseLLMClient.
        For now, we'll implement it here using the base client's session if possible,
        but BaseLLMClient creates a new client per request currently.
        We'll keep the implementation similar but use standardized logging.
        """
        import httpx
        
        self.logger.debug("Downloading document", extra={"document_url": document_url})

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/pdf, image/*, */*",
            }
        ) as client:
            try:
                response = await client.get(document_url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")
                if "pdf" not in content_type.lower() and "image" not in content_type.lower():
                    self.logger.warning(
                        "Unexpected content type",
                        extra={"content_type": content_type, "document_url": document_url},
                    )

                self.logger.debug(
                    "Document downloaded successfully",
                    extra={
                        "document_url": document_url,
                        "content_type": content_type,
                        "size_bytes": len(response.content),
                    },
                )

                return response.content

            except Exception as e:
                self.logger.error(
                    "Failed to download document",
                    exc_info=True,
                    extra={"document_url": document_url, "error": str(e)},
                )
                raise InvalidDocumentError(f"Failed to download document: {str(e)}") from e
