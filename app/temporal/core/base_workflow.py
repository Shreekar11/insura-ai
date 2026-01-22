from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseWorkflow(ABC):
    """Abstract base class for all Temporal workflows."""
    
    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Main execution method for the workflow."""
        pass
