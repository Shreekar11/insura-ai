"""Entity resolution activities for Phase 3.

These activities handle entity aggregation, resolution, and relationship extraction.
"""

from temporalio import activity
from typing import Dict, List
from uuid import UUID

from app.core.database import async_session_maker
from app.pipeline.entity_resolution import EntityResolutionPipeline
from app.repositories.entity_repository import EntityRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@activity.defn
async def aggregate_document_entities(workflow_id: str, document_id: str) -> Dict:
    """Aggregate entities from all chunks for the document."""
    try:
        activity.logger.info(f"[Phase 3: Entity Resolution] Aggregating entities for document: {document_id}")
        
        async with async_session_maker() as session:
            pipeline = EntityResolutionPipeline(session)
            result = await pipeline.aggregate_entities(document_id=UUID(document_id), workflow_id=UUID(workflow_id))
            
            activity.logger.info(
                f"[Phase 3: Entity Resolution] Entity aggregation complete for {document_id} with workflow {workflow_id}: "
                f"{result['unique_entities']} unique entities from {result['total_chunks']} chunks"
            )
            
            return result
        
    except Exception as e:
        activity.logger.error(f"Entity aggregation failed for {document_id}: {e}")
        raise


@activity.defn
async def resolve_canonical_entities(workflow_id: str, document_id: str, aggregated_data: Dict) -> List[str]:
    """Resolve aggregated entities to canonical forms."""
    try:
        entities = aggregated_data.get('entities', [])
        activity.logger.info(f"[Phase 3: Entity Resolution] Resolving {len(entities)} entities to canonical forms")
        
        async with async_session_maker() as session:
            pipeline = EntityResolutionPipeline(session)
            canonical_ids = await pipeline.resolve_canonical_entities(
                document_id=UUID(document_id),
                workflow_id=UUID(workflow_id),
                entities=entities,
            )
            
            await session.commit()
            
            canonical_id_strings = [str(id) for id in canonical_ids]
            activity.logger.info(
                f"[Phase 3: Entity Resolution] Canonical resolution complete: {len(canonical_id_strings)} canonical entities"
            )
            
            return canonical_id_strings
        
    except Exception as e:
        activity.logger.error(f"Canonical entity resolution failed: {e}")
        raise


@activity.defn
async def extract_relationships(workflow_id: str, document_id: str) -> List[Dict]:
    """Extract relationships between canonical entities (Pass 2)."""
    try:
        activity.logger.info(f"[Phase 3: Entity Resolution] Extracting relationships for document: {document_id}")
        activity.heartbeat("Starting relationship extraction")
        
        async with async_session_maker() as session:
            pipeline = EntityResolutionPipeline(session)
            relationship_records = await pipeline.extract_relationships(
                document_id=UUID(document_id),
                workflow_id=UUID(workflow_id),
            )
            
            await session.commit()
            
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
                f"[Phase 3: Entity Resolution] Relationship extraction complete for {document_id}: "
                f"{len(relationships)} relationships extracted"
            )
            
            return relationships
        
    except Exception as e:
        activity.logger.error(f"Relationship extraction failed for {document_id}: {e}")
        raise


@activity.defn
async def rollback_entities(entity_ids: List[str]) -> None:
    """Compensating activity: Delete entities if workflow fails."""
    try:
        if not entity_ids:
            return
            
        activity.logger.warning(
            f"SAGA ROLLBACK: Deleting {len(entity_ids)} entities due to workflow failure"
        )
        
        async with async_session_maker() as session:
            entity_repo = EntityRepository(session)
            for entity_id in entity_ids:
                await entity_repo.delete(UUID(entity_id))
            await session.commit()
    except Exception as e:
        activity.logger.error(f"Entity rollback failed: {e}")
        raise