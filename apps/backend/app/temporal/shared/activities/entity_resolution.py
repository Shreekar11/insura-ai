"""Entity resolution activities for Phase 3."""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from app.database.models import StepSectionOutput
from app.core.database import async_session_maker
from app.pipeline.entity_resolution import EntityResolutionPipeline
from app.repositories.entity_repository import EntityRepository
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry

LOGGER = get_logger(__name__)


@ActivityRegistry.register("shared", "aggregate_document_entities")
@activity.defn
async def aggregate_document_entities(workflow_id: str, document_id: str, rich_context: Optional[Dict] = None) -> Dict:
    """Aggregate entities from all chunks for the document."""
    try:
        async with async_session_maker() as session:
            # Load StepSectionOutputs for this document/workflow
            stmt = select(StepSectionOutput).where(
                StepSectionOutput.document_id == UUID(document_id),
                StepSectionOutput.workflow_id == UUID(workflow_id)
            )
            result = await session.execute(stmt)
            section_outputs = result.scalars().all()
            
            # Prepare rich context
            if rich_context is None:
                rich_context = {}
            
            rich_context["step_section_outputs"] = [
                {
                    "section_type": so.section_type,
                    "display_payload": so.display_payload
                } for so in section_outputs
            ]

            pipeline = EntityResolutionPipeline(session)
            result = await pipeline.aggregate_entities(
                document_id=UUID(document_id),
                workflow_id=UUID(workflow_id),
                rich_context=rich_context
            )

            # FIX VERIFICATION: Log aggregation results for monitoring
            LOGGER.info(
                f"Entity aggregation completed",
                extra={
                    "document_id": document_id,
                    "workflow_id": workflow_id,
                    "total_entities": result.get("total_entities"),
                    "unique_entities": result.get("unique_entities"),
                }
            )

            return result
    except Exception as e:
        activity.logger.error(f"Entity aggregation failed for {document_id}: {e}")
        raise


@ActivityRegistry.register("shared", "resolve_canonical_entities")
@activity.defn
async def resolve_canonical_entities(workflow_id: str, document_id: str, aggregated_data: Dict) -> List[str]:
    """Resolve aggregated entities to canonical forms."""
    try:
        entities = aggregated_data.get('entities', [])
        async with async_session_maker() as session:
            pipeline = EntityResolutionPipeline(session)
            canonical_ids = await pipeline.resolve_canonical_entities(
                document_id=UUID(document_id),
                workflow_id=UUID(workflow_id),
                entities=entities,
            )
            await session.commit()

            # FIX VERIFICATION: Log resolution completion
            LOGGER.info(
                f"Canonical entities resolved",
                extra={
                    "document_id": document_id,
                    "workflow_id": workflow_id,
                    "canonical_entities_count": len(canonical_ids),
                }
            )

            return [str(id) for id in canonical_ids]
    except Exception as e:
        activity.logger.error(f"Canonical entity resolution failed: {e}")
        raise


@ActivityRegistry.register("shared", "extract_relationships")
@activity.defn
async def extract_relationships(workflow_id: str, document_id: str) -> List[Dict]:
    """Extract relationships between canonical entities (Legacy)."""
    # Simply call compute and then persist for backward compatibility
    rel_data = await extract_relationships_compute(workflow_id, document_id)
    return await persist_relationships(workflow_id, document_id, rel_data)


@ActivityRegistry.register("shared", "extract_relationships_compute")
@activity.defn
async def extract_relationships_compute(workflow_id: str, document_id: str) -> List[Dict]:
    """Extract relationships (COMPUTE ONLY) with idempotency check."""
    from app.repositories.entity_repository import EntityRelationshipRepository
    try:
        async with async_session_maker() as session:
            # 1. Idempotency Check (Read-Before-Write)
            # RelationshipExtractorGlobal.get_idempotency_key(document_id, workflow_id)
            # But wait, RelationshipExtractorGlobal returns a LIST. 
            # We check if any relationship already exists for this workflow/document.
            rel_repo = EntityRelationshipRepository(session)
            existing = await rel_repo.get_by_workflow(UUID(workflow_id))
            if existing:
                LOGGER.info(f"Relationships already exist for workflow {workflow_id}, skipping compute")
                return [{
                    "id": str(rel.id),
                    "source_entity_id": str(rel.source_entity_id) if rel.source_entity_id else None,
                    "target_entity_id": str(rel.target_entity_id) if rel.target_entity_id else None,
                    "relationship_type": rel.relationship_type,
                    "attributes": rel.attributes,
                    "confidence": float(rel.confidence) if rel.confidence else None,
                } for rel in existing]

            pipeline = EntityResolutionPipeline(session)
            relationship_data = await pipeline.extract_relationships_compute(
                document_id=UUID(document_id),
                workflow_id=UUID(workflow_id),
            )
            return relationship_data
    except Exception as e:
        activity.logger.error(f"Relationship extraction compute failed for {document_id}: {e}")
        raise


@ActivityRegistry.register("shared", "persist_relationships")
@activity.defn
async def persist_relationships(workflow_id: str, document_id: str, relationships_data: List[Dict]) -> List[Dict]:
    """Persist relationships (PERSIST ONLY)."""
    try:
        async with async_session_maker() as session:
            pipeline = EntityResolutionPipeline(session)
            relationship_records = await pipeline.persist_relationships(
                document_id=UUID(document_id),
                relationships=relationships_data,
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
            return relationships
    except Exception as e:
        activity.logger.error(f"Relationship persistence failed for {document_id}: {e}")
        raise


@ActivityRegistry.register("shared", "rollback_entities")
@activity.defn
async def rollback_entities(entity_ids: List[str]) -> None:
    """Compensating activity: Delete entities if workflow fails."""
    try:
        if not entity_ids:
            return
        async with async_session_maker() as session:
            entity_repo = EntityRepository(session)
            for entity_id in entity_ids:
                await entity_repo.delete(UUID(entity_id))
            await session.commit()
    except Exception as e:
        activity.logger.error(f"Entity rollback failed: {e}")
        raise
