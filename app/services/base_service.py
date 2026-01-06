from typing import Optional, Any, Dict, List
from abc import ABC, abstractmethod

from app.repositories.base_repository import BaseRepository
from app.core.exceptions import AppError, ValidationError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class BaseService(ABC):
    """Base class for application services.
    
    Provides a standardized execution flow with validation and error handling.
    """

    def __init__(self, repository: Optional[BaseRepository] = None):
        """Initialize the service.
        
        Args:
            repository: Optional primary repository for the service
        """
        self.repository = repository
        self.logger = LOGGER

    async def execute(self, *args, **kwargs) -> Any:
        """Execute the service logic.
        
        This template method handles:
        1. Input validation
        2. Core logic execution
        3. Standardized error handling
        
        Args:
            *args: Positional arguments for the service
            **kwargs: Keyword arguments for the service
            
        Returns:
            Result of the service execution
            
        Raises:
            AppError: If execution fails
        """
        try:
            self.validate(*args, **kwargs)
            
            result = await self.run(*args, **kwargs)
            
            return result
            
        except AppError:
            raise
            
        except Exception as e:
            self.logger.error(
                f"Service execution failed: {str(e)}",
                exc_info=True,
                extra={"service": self.__class__.__name__}
            )
            raise AppError(f"Service execution failed: {str(e)}", original_error=e)

    def validate(self, *args, **kwargs):
        """Validate service input.
        
        Override this method to implement custom validation logic.
        
        Raises:
            ValidationError: If input is invalid
        """
        pass

    @abstractmethod
    async def run(self, *args, **kwargs) -> Any:
        """Run the core service logic.
        
        Must be implemented by subclasses.
        """
        pass
