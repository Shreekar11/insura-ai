"""Extracted Stage Facade - orchestrates section field and entity extraction."""

from uuid import UUID
from app.core.base_stage import BaseStage, StageResult, StageStatus
from .services.extract_sections import ExtractSectionsService
from .services.extract_entities import ExtractEntitiesService


class ExtractedStageFacade(BaseStage):
    """
    Extracted stage: We extracted insurance data.
    
    Coordinates:
    - Section field extraction
    - Entity extraction
    """
    
    def __init__(
        self,
        extract_sections: ExtractSectionsService,
        extract_entities: ExtractEntitiesService,
    ):
        self._extract_sections = extract_sections
        self._extract_entities = extract_entities
    
    @property
    def name(self) -> str:
        return "extracted"
    
    @property
    def dependencies(self) -> list[str]:
        return ["classified"]
    
    async def is_complete(self, document_id: UUID) -> bool:
        """Check if extraction results already exist."""
        # Implementation would check section extraction repository
        pass
    
    async def execute(self, document_id: UUID, *args, **kwargs) -> StageResult:
        """Execute the Extracted stage."""
        # 1. Extract sections
        section_results = await self._extract_sections.execute(document_id)
        
        # 2. Extract entities
        entity_results = await self._extract_entities.execute(document_id)
        
        return StageResult(
            status=StageStatus.COMPLETED,
            data={
                "sections_extracted": len(section_results),
                "total_entities": entity_results.total_entities,
            }
        )
