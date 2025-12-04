"""Entity resolution activities that wrap existing entity services.

These activities provide Temporal-compatible wrappers around:
- app/services/pipeline/document_entity_aggregator.py - Entity aggregation
- app/services/entity/resolver.py - Canonical entity resolution
- app/services/entity/global_relationship_extractor.py - Relationship extraction
"""

from temporalio import activity
from typing import Dict, List
from uuid import UUID

from app.services.pipeline.document_entity_aggregator import DocumentEntityAggregator
from app.services.entity.resolver import EntityResolver
from app.services.entity.global_relationship_extractor import RelationshipExtractorGlobal
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
        
        from app.database.session import get_session
        async with get_session() as session:
            aggregator = DocumentEntityAggregator(session)
            
            # Aggregate entities from all chunks
            result = await aggregator.aggregate_entities(UUID(document_id))
            
            activity.logger.info(
                f"Entity aggregation complete for {document_id}: "
                f"{len(result.get('entities', []))} entities aggregated"
            )
            
            return result
        
    except Exception as e:
        activity.logger.error(f"Entity aggregation failed for {document_id}: {e}")
        raise


@activity.defn
async def resolve_canonical_entities(aggregated_data: Dict) -> List[str]:
    """
    Resolve aggregated entities to canonical forms.
    
    Uses existing EntityResolver service.
    
    Args:
        aggregated_data: Aggregated entity data from previous activity
        
    Returns:
        List of canonical entity IDs
    """
    try:
        entities = aggregated_data.get('entities', [])
        activity.logger.info(f"Resolving {len(entities)} entities to canonical forms")
        
        from app.database.session import get_session
        async with get_session() as session:
            resolver = EntityResolver(session)
            
            # Resolve to canonical entities
            canonical_ids = await resolver.resolve_entities(entities)
            
            activity.logger.info(
                f"Canonical resolution complete: {len(canonical_ids)} canonical entities"
            )
            
            return canonical_ids
        
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
        
        from app.database.session import get_session
        async with get_session() as session:
            extractor = RelationshipExtractorGlobal(session)
            
            # Extract relationships
            relationships = await extractor.extract_relationships(UUID(document_id))
            
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
        activity.logger.warning(
            f"SAGA ROLLBACK: Deleting {len(entity_ids)} entities due to workflow failure"
        )
        
        from app.database.session import get_session
        from app.repositories.entity_repository import EntityRepository
        
        async with get_session() as session:
            entity_repo = EntityRepository(session)
            
            # Delete entities
            for entity_id in entity_ids:
                await entity_repo.delete_entity(UUID(entity_id))
            
            await session.commit()
            
            activity.logger.info(f"Successfully rolled back {len(entity_ids)} entities")
        
    except Exception as e:
        activity.logger.error(f"Entity rollback failed: {e}")
        # Don't raise - rollback is best-effort
