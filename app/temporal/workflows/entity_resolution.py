"""Entity Resolution child workflow with Saga pattern.

This workflow orchestrates entity resolution using activity string names
to avoid importing non-deterministic modules.
"""

from temporalio import workflow
from datetime import timedelta


@workflow.defn
class EntityResolutionWorkflow:
    """Child workflow for entity aggregation, canonical resolution, and relationship extraction."""
    
    @workflow.run
    async def run(self, document_id: str) -> dict:
        """
        Aggregate entities, resolve to canonical forms, and extract relationships.
        
        Implements saga pattern with compensating rollback on failure.
        
        Args:
            document_id: UUID of the document to process
            
        Returns:
            Dictionary with entity_count and relationship_count
        """
        entity_ids = []
        
        try:
            # Aggregate entities from all chunks (already extracted during normalization)
            aggregated = await workflow.execute_activity(
                "aggregate_document_entities",
                document_id,
                start_to_close_timeout=timedelta(minutes=5),
            )
            
            # Resolve to canonical entities
            entity_ids = await workflow.execute_activity(
                "resolve_canonical_entities",
                args=[document_id, aggregated],
                start_to_close_timeout=timedelta(minutes=3),
            )
            
            # Extract relationships (Pass 2)
            relationships = await workflow.execute_activity(
                "extract_relationships",
                document_id,
                start_to_close_timeout=timedelta(minutes=10),
            )
            
            return {
                "entity_count": len(entity_ids),
                "relationship_count": len(relationships),
            }
            
        except Exception as e:
            # Saga compensation: rollback entities
            if entity_ids:
                workflow.logger.warning(f"Rolling back {len(entity_ids)} entities due to error: {e}")
                await workflow.execute_activity(
                    "rollback_entities",
                    args=[entity_ids],
                    start_to_close_timeout=timedelta(minutes=1),
                )
            raise
