"""Enriched Stage Facade - orchestrates entity resolution and relationship extraction."""

from uuid import UUID
from app.core.base_stage import BaseStage, StageResult, StageStatus
from .services.resolve_entities import ResolveEntitiesService
from .services.extract_relationships import ExtractRelationshipsService


class EnrichedStageFacade(BaseStage):
    """
    Enriched stage: We connected, validated, and reconciled data.
    
    Coordinates:
    - Entity resolution
    - Relationship extraction
    """
    
    def __init__(
        self,
        resolve_entities: ResolveEntitiesService,
        extract_relationships: ExtractRelationshipsService,
    ):
        self._resolve_entities = resolve_entities
        self._extract_relationships = extract_relationships
    
    @property
    def name(self) -> str:
        return "enriched"
    
    @property
    def dependencies(self) -> list[str]:
        return ["extracted"]
    
    async def is_complete(self, document_id: UUID) -> bool:
        """Check if enrichment results already exist."""
        # Implementation would check entity resolution repository
        pass
    
    async def execute(self, document_id: UUID, *args, **kwargs) -> StageResult:
        """Execute the Enriched stage."""
        # 1. Resolve entities
        resolution_results = await self._resolve_entities.execute(document_id)
        
        # 2. Extract relationships
        relationship_results = await self._extract_relationships.execute(document_id)
        
        return StageResult(
            status=StageStatus.COMPLETED,
            data={
                "entities_resolved": resolution_results.resolved_count,
                "relationships_found": relationship_results.total_relationships,
            }
        )
