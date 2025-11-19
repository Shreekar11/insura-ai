"""Pydantic request models for OCR API endpoints."""

from pydantic import BaseModel, Field, HttpUrl, field_validator

class OCRExtractionRequest(BaseModel):
    """Request model for OCR extraction endpoint.

    Attributes:
        pdf_url: Public URL of the PDF document to process
    """

    pdf_url: HttpUrl = Field(
        ...,
        description="Public URL of the PDF document to extract text from",
        examples=["https://example.com/document.pdf"],
    )
    normalize: bool = Field(
        default=True,
        description="Apply text normalization for insurance documents",
    )

    @field_validator("pdf_url")
    @classmethod
    def validate_pdf_url(cls, v: HttpUrl) -> HttpUrl:
        """Validate that the URL is accessible.

        Args:
            v: URL to validate

        Returns:
            HttpUrl: Validated URL

        Raises:
            ValueError: If URL is invalid
        """
        url_str = str(v)
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "pdf_url": "https://example.com/insurance-policy.pdf",
                    "normalize": True,
                }
            ]
        }
    }

class OCRNormalizeRequest(BaseModel):
    """Request model for text normalization.
    
    Attributes:
        text: Raw OCR text to normalize
    """
    
    text: str = Field(
        ...,
        description="Raw OCR-extracted text to normalize",
        min_length=1,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "Raw OCR-extracted text to normalize",
                }
            ]
        }
    }

