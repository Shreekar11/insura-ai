"""Entity resolution activities that wrap existing entity services.

These activities provide Temporal-compatible wrappers around:
- app/services/pipeline/document_entity_aggregator.py - Entity aggregation
- app/services/entity/resolver.py - Canonical entity resolution
- app/services/entity/global_relationship_extractor.py - Relationship extraction
"""

from temporalio import activity
from typing import Dict, List
from uuid import UUID

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def aggregate_document_entities(document_id: str) -> Dict:
    """
    Aggregate entities from all chunks for the document.
    
    Uses existing DocumentEntityAggregator service.
    
    Args:
        document_id: UUID of the document
        
    Returns:
        Dictionary with aggregated entity data
    """
    try:
        activity.logger.info(f"Aggregating entities for document: {document_id}")
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from app.services.pipeline.document_entity_aggregator import DocumentEntityAggregator
        
        async with async_session_maker() as session:
            aggregator = DocumentEntityAggregator(session)
            
            # Aggregate entities from all chunks
            aggregated = await aggregator.aggregate_entities(UUID(document_id))
            
            # Convert to serializable format
            result = {
                "entities": aggregated.entities,
                "total_chunks": aggregated.total_chunks,
                "total_entities": aggregated.total_entities,
                "unique_entities": aggregated.unique_entities,
                "document_id": document_id,
            }
            
            activity.logger.info(
                f"Entity aggregation complete for {document_id}: "
                f"{aggregated.unique_entities} unique entities from {aggregated.total_chunks} chunks"
            )
            
            return result
        
    except Exception as e:
        activity.logger.error(f"Entity aggregation failed for {document_id}: {e}")
        raise


@activity.defn
async def resolve_canonical_entities(document_id: str, aggregated_data: Dict) -> List[str]:
    """
    Resolve aggregated entities to canonical forms.
    
    Uses existing EntityResolver service.
    
    Args:
        document_id: UUID of the document
        aggregated_data: Aggregated entity data from previous activity
        
    Returns:
        List of canonical entity IDs
    """
    try:
        entities = aggregated_data.get('entities', [])
        activity.logger.info(f"Resolving {len(entities)} entities to canonical forms")
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from app.services.entity.resolver import EntityResolver
        
        async with async_session_maker() as session:
            resolver = EntityResolver(session)
            
            # Resolve to canonical entities
            canonical_ids = await resolver.resolve_entities_batch(
                entities=entities,
                chunk_id=None,  # Document-level, not chunk-specific
                document_id=UUID(document_id)
            )
            
            await session.commit()
            
            # Convert UUIDs to strings for serialization
            canonical_id_strings = [str(id) for id in canonical_ids]
            
            activity.logger.info(
                f"Canonical resolution complete: {len(canonical_id_strings)} canonical entities"
            )
            
            return canonical_id_strings
        
    except Exception as e:
        activity.logger.error(f"Canonical entity resolution failed: {e}")
        raise


@activity.defn
async def extract_relationships(document_id: str) -> List[Dict]:
    """
    Extract relationships between canonical entities (Pass 2).
    
    Uses existing RelationshipExtractorGlobal service.
    
    Args:
        document_id: UUID of the document
        
    Returns:
        List of extracted relationships
    """
    try:
        activity.logger.info(f"Extracting relationships for document: {document_id}")
        
        # Heartbeat for long-running operation
        activity.heartbeat("Starting relationship extraction")
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from app.services.entity.global_relationship_extractor import RelationshipExtractorGlobal
        
        async with async_session_maker() as session:
            extractor = RelationshipExtractorGlobal(
                session=session,
                provider=settings.llm_provider,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                openrouter_api_key=settings.openrouter_api_key if settings.llm_provider == "openrouter" else None,
                openrouter_model=settings.openrouter_model,
                openrouter_api_url=settings.openrouter_api_url,
            )
            
            # Extract relationships
            relationship_records = await extractor.extract_relationships(UUID(document_id))
            
            await session.commit()
            
            # Convert to serializable format
            relationships = []
            for rel in relationship_records:
                relationships.append({
                    "id": str(rel.id),
                    "source_entity_id": str(rel.source_entity_id) if rel.source_entity_id else None,
                    "target_entity_id": str(rel.target_entity_id) if rel.target_entity_id else None,
                    "relationship_type": rel.relationship_type,
                    "attributes": rel.attributes,
                    "confidence": float(rel.confidence) if rel.confidence else None,
                })
            
            activity.logger.info(
                f"Relationship extraction complete for {document_id}: "
                f"{len(relationships)} relationships extracted"
            )
            
            return relationships
        
    except Exception as e:
        activity.logger.error(f"Relationship extraction failed for {document_id}: {e}")
        raise


@activity.defn
async def rollback_entities(entity_ids: List[str]) -> None:
    """
    Compensating activity: Delete entities if workflow fails.
    
    This is part of the saga pattern for distributed transaction safety.
    
    Args:
        entity_ids: List of entity IDs to delete
    """
    try:
        if not entity_ids:
            activity.logger.info("No entities to rollback")
            return
            
        activity.logger.warning(
            f"SAGA ROLLBACK: Deleting {len(entity_ids)} entities due to workflow failure"
        )
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from sqlalchemy import delete
        from app.database.models import CanonicalEntity
        
        async with async_session_maker() as session:
            # Delete entities in batch
            for entity_id in entity_ids:
                try:
                    stmt = delete(CanonicalEntity).where(CanonicalEntity.id == UUID(entity_id))
                    await session.execute(stmt)
                except Exception as e:
                    activity.logger.warning(f"Failed to delete entity {entity_id}: {e}")
            
            await session.commit()
            
            activity.logger.info(f"Successfully rolled back {len(entity_ids)} entities")
        
    except Exception as e:
        activity.logger.error(f"Entity rollback failed: {e}")
        # Don't raise - rollback is best-effort
