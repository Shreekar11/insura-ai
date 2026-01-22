"""Base stage interface for all semantic processing stages."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, List
from uuid import UUID


class StageStatus(Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageResult:
    """Standard result from stage execution."""
    status: StageStatus
    data: dict[str, Any]
    error: Optional[str] = None


class BaseStage(ABC):
    """Base class for semantic processing stages."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name (processed, classified, etc.)."""
        pass
    
    @property
    @abstractmethod
    def dependencies(self) -> list[str]:
        """Stages that must complete before this one."""
        pass
    
    @abstractmethod
    async def is_complete(self, document_id: UUID) -> bool:
        """Check if stage is complete for document."""
        pass
    
    @abstractmethod
    async def execute(self, document_id: UUID, *args, **kwargs) -> StageResult:
        """Execute the stage."""
        pass
