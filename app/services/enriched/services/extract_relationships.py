"""Extract relationships service - identifies connections between entities."""

from uuid import UUID
from app.services.enriched.contracts import RelationshipResult
from app.services.enriched.services.entity.global_relationship_extractor import RelationshipExtractorGlobal


class ExtractRelationshipsService:
    """Service for identifying relationships between resolved entities."""
    
    def __init__(self, extractor: RelationshipExtractorGlobal):
        self._extractor = extractor
    
    async def execute(self, document_id: UUID) -> RelationshipResult:
        """Extract relationships from document context."""
        # Implementation would call self._extractor
        pass
