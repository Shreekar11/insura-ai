"""Normalization child workflow.

This workflow orchestrates normalization using activity string names
to avoid importing non-deterministic modules.
"""

from temporalio import workflow
from datetime import timedelta


@workflow.defn
class NormalizationWorkflow:
    """Child workflow for document normalization, classification, and entity extraction."""
    
    @workflow.run
    async def run(self, document_id: str) -> dict:
        """
        Normalize document, extract classification signals, and extract entities.
        
        Args:
            document_id: UUID of the document to process
            
        Returns:
            Dictionary with chunk_count, normalized_count, entity_count, and classification
        """
        # Execute normalization (includes chunking, classification, entity extraction)
        result = await workflow.execute_activity(
            "normalize_and_classify_document",
            document_id,
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=workflow.RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        return {
            "chunk_count": result['chunk_count'],
            "normalized_count": result['normalized_count'],
            "entity_count": result['entity_count'],
            "classification": result['classification'],
        }
