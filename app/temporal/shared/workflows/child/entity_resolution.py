"""Entity Resolution child workflow with Saga pattern."""

from temporalio import workflow
from datetime import timedelta
from typing import Optional, Dict, List

from app.utils.workflow_schemas import (
    EntityResolutionOutputSchema,
    validate_workflow_output,
)
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class EntityResolutionWorkflow:
    """Child workflow for entity aggregation, canonical resolution, and relationship extraction."""
    
    @workflow.run
    async def run(self, workflow_id: str, document_id: str) -> dict:
        """Aggregate entities, resolve to canonical forms, and extract relationships."""
        entity_ids = []
        
        try:
            aggregated = await workflow.execute_activity(
                "aggregate_document_entities",
                args=[workflow_id, document_id],
                start_to_close_timeout=timedelta(minutes=5),
            )
            
            entity_ids = await workflow.execute_activity(
                "resolve_canonical_entities",
                args=[workflow_id, document_id, aggregated],
                start_to_close_timeout=timedelta(minutes=3),
            )
            
            relationships = await workflow.execute_activity(
                "extract_relationships",
                args=[workflow_id, document_id],
                start_to_close_timeout=timedelta(minutes=10),
            )
            
            output = {
                "entity_count": len(entity_ids),
                "relationship_count": len(relationships),
            }
            
            return validate_workflow_output(
                output,
                EntityResolutionOutputSchema,
                "EntityResolutionWorkflow"
            )
            
        except Exception as e:
            if entity_ids:
                await workflow.execute_activity(
                    "rollback_entities",
                    args=[entity_ids],
                    start_to_close_timeout=timedelta(minutes=1),
                )
            raise
