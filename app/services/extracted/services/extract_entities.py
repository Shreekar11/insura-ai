"""Extract entities service - performs entity extraction and aggregation."""

from uuid import UUID
from app.services.extracted.contracts import EntityExtractionResult
from app.services.enriched.services.entity.entity_aggregator import EntityAggregator


class ExtractEntitiesService:
    """Service for identifying and aggregating document entities."""
    
    def __init__(self, aggregator: EntityAggregator):
        self._aggregator = aggregator
    
    async def execute(self, document_id: UUID) -> EntityExtractionResult:
        """Extract and aggregate entities from document."""
        # Implementation would call self._aggregator
        pass
