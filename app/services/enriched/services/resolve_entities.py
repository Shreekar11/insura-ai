"""Resolve entities service - performs canonical entity resolution."""

from uuid import UUID
from app.services.enriched.contracts import ResolutionResult
from app.services.enriched.services.entity.resolver import EntityResolver


class ResolveEntitiesService:
    """Service for reconciling entity mentions into canonical entities."""
    
    def __init__(self, resolver: EntityResolver):
        self._resolver = resolver
    
    async def execute(self, document_id: UUID) -> ResolutionResult:
        """Resolve all entity mentions in document."""
        # Implementation would call self._resolver
        pass
