class AppError(Exception):
    """Base exception for application errors."""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error

class APIClientError(AppError):
    """Raised when an external API call fails."""
    pass

class APITimeoutError(APIClientError):
    """Raised when an external API call times out."""
    pass

class DatabaseError(AppError):
    """Raised when a database operation fails."""
    pass

class ValidationError(AppError):
    """Raised when input validation fails."""
    pass

class ConfigurationError(AppError):
    """Raised when configuration is invalid or missing."""
    pass
