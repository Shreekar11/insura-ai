"""Custom exception classes for the application."""


class InsuranceAIException(Exception):
    """Base exception for all application errors."""

    pass


class OCRServiceException(InsuranceAIException):
    """Base exception for OCR service errors."""

    pass


class OCRExtractionError(OCRServiceException):
    """Exception raised when OCR extraction fails."""

    pass


class OCRTimeoutError(OCRServiceException):
    """Exception raised when OCR processing times out."""

    pass


class InvalidDocumentError(OCRServiceException):
    """Exception raised when document is invalid or cannot be processed."""

    pass


class APIClientError(InsuranceAIException):
    """Exception raised when external API call fails."""

    pass


class ConfigurationError(InsuranceAIException):
    """Exception raised when configuration is invalid or missing."""

    pass

