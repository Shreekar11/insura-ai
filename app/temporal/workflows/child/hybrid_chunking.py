"""Phase 3: Hybrid Chunking child workflow.

This workflow orchestrates section-aware hybrid chunking using Docling.
Now accepts page_section_map from manifest to ensure consistent section
assignment with Phase 0 page analysis.
"""

from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta
from typing import Optional, Dict

from app.utils.workflow_schemas import (
    HybridChunkingOutputSchema,
    validate_workflow_output,
)


@workflow.defn
class HybridChunkingWorkflow:
    """Child workflow for hybrid chunking with section awareness."""
    
    @workflow.run
    async def run(
        self, 
        workflow_id: str,
        document_id: str,
        page_section_map: Optional[Dict[int, str]] = None,
    ) -> dict:
        """
        Perform hybrid chunking on document pages.
        
        This workflow:
        1. Retrieves OCR-extracted pages
        2. Uses page_section_map from manifest for section assignment (if provided)
        3. Performs hybrid chunking using Docling
        4. Creates section super-chunks
        5. Persists results to database
        
        Args:
            document_id: UUID of the document to chunk
            page_section_map: Optional mapping of page numbers to section types
                from Phase 0 page analysis manifest. If provided, this ensures
                consistent section assignment without re-detection.
            
        Returns:
            Dictionary with chunking statistics
        """
        # Normalize empty dict to None
        if page_section_map == {}:
            page_section_map = None
        
        has_section_map = page_section_map is not None
        workflow.logger.info(
            f"Starting hybrid chunking workflow for document: {document_id} "
            f"(section_map: {'provided' if has_section_map else 'auto-detect'})",
            extra={
                "workflow_id": workflow_id,
                "document_id": document_id,
                "page_section_map": page_section_map,
            }
        )
        
        # Execute hybrid chunking activity with section map
        result = await workflow.execute_activity(
            "perform_hybrid_chunking",
            args=[workflow_id, document_id, page_section_map],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        
        workflow.logger.info(
            f"Hybrid chunking complete: {result['chunk_count']} chunks, "
            f"{result['super_chunk_count']} super-chunks, "
            f"{len(result['sections_detected'])} sections detected "
            f"(source: {result.get('section_source', 'unknown')})"
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
        
        # Validate output against schema (fail fast if invalid)
        validated_output = validate_workflow_output(
            output,
            HybridChunkingOutputSchema,
            "HybridChunkingWorkflow"
        )
        
        workflow.logger.info("Hybrid chunking output validated against schema")
        
        return validated_output

