"""Phase 3: Entity Resolution facade.

Combines DocumentEntityAggregator, EntityResolver, and RelationshipExtractorGlobal.
"""

from typing import List, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.pipeline.document_entity_aggregator import DocumentEntityAggregator
from app.services.entity.resolver import EntityResolver
from app.services.entity.global_relationship_extractor import RelationshipExtractorGlobal
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EntityResolutionPipeline:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.aggregator = DocumentEntityAggregator(session)
        self.resolver = EntityResolver(session)
        self.relationship_extractor = RelationshipExtractorGlobal(
            session=session,
            provider=settings.llm_provider,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openrouter_api_key=settings.openrouter_api_key if settings.llm_provider == "openrouter" else None,
            openrouter_model=settings.openrouter_model,
            openrouter_api_url=settings.openrouter_api_url,
        )

    async def aggregate_entities(self, document_id: UUID) -> Dict:
        """Aggregate entities from all chunks."""
        aggregated = await self.aggregator.aggregate_entities(document_id)
        return {
            "entities": aggregated.entities,
            "total_chunks": aggregated.total_chunks,
            "total_entities": aggregated.total_entities,
            "unique_entities": aggregated.unique_entities,
            "document_id": str(document_id),
        }

    async def resolve_canonical_entities(self, document_id: UUID, entities: List[Dict]) -> List[UUID]:
        """Resolve aggregated entities to canonical forms."""
        canonical_ids = await self.resolver.resolve_entities_batch(
            entities=entities,
            chunk_id=None,
            document_id=document_id
        )
        return canonical_ids

    async def extract_relationships(self, document_id: UUID) -> List[Any]:
        """Extract relationships between canonical entities."""
        return await self.relationship_extractor.extract_relationships(document_id)

