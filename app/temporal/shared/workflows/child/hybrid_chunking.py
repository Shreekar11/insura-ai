"""Phase 3: Hybrid Chunking child workflow."""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Optional, Dict, List

from app.utils.workflow_schemas import (
    HybridChunkingOutputSchema,
    validate_workflow_output,
)
from app.temporal.core.workflow_registry import WorkflowRegistry, WorkflowType


@WorkflowRegistry.register(category=WorkflowType.SHARED)
@workflow.defn
class HybridChunkingWorkflow:
    """Child workflow for hybrid chunking with section awareness."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
        page_section_map: Optional[Dict[int, str]] = None,
        target_sections: Optional[List[str]] = None,
        section_boundaries: Optional[List[Dict]] = None,
    ) -> dict:
        """Perform hybrid chunking on document pages."""
        if page_section_map == {}:
            page_section_map = None
        
        result = await workflow.execute_activity(
            "perform_hybrid_chunking",
            args=[workflow_id, document_id, page_section_map, target_sections, section_boundaries],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        output = {
            "chunk_count": result["chunk_count"],
            "super_chunk_count": result["super_chunk_count"],
            "sections_detected": result["sections_detected"],
            "section_stats": result["section_stats"],
            "total_tokens": result["total_tokens"],
            "avg_tokens_per_chunk": result["avg_tokens_per_chunk"],
            "section_source": result.get("section_source", "unknown"),
        }
        
        return validate_workflow_output(
            output,
            HybridChunkingOutputSchema,
            "HybridChunkingWorkflow"
        )
