"""Temporal worker service for document processing.

This worker:
- Connects to local Temporal server (localhost:7233)
- Registers all workflows and activities
- Polls the documents-queue task queue
- Handles concurrent execution with configured limits
"""

import asyncio
import os
from temporalio.client import Client
from temporalio.worker import Worker

# Import all child workflows
from app.temporal.workflows.process_document import ProcessDocumentWorkflow
from app.temporal.workflows.child.ocr_extraction import OCRExtractionWorkflow
from app.temporal.workflows.child.table_extraction import TableExtractionWorkflow
from app.temporal.workflows.child.page_analysis import PageAnalysisWorkflow
from app.temporal.workflows.child.hybrid_chunking import HybridChunkingWorkflow
from app.temporal.workflows.child.extraction import ExtractionWorkflow
from app.temporal.workflows.child.entity_resolution import EntityResolutionWorkflow
from app.temporal.workflows.child.indexing import IndexingWorkflow

# Import all stages workflows
from app.temporal.workflows.stages.processed import ProcessedStageWorkflow
from app.temporal.workflows.stages.extracted import ExtractedStageWorkflow
from app.temporal.workflows.stages.enriched import EnrichedStageWorkflow
from app.temporal.workflows.stages.summarized import SummarizedStageWorkflow
from app.temporal.workflows.policy_comparison import PolicyComparisonWorkflow

# Import all activities
from app.temporal.activities.ocr_extraction import extract_ocr
from app.temporal.activities.table_extraction import extract_tables
from app.temporal.activities import page_analysis
from app.temporal.activities.hybrid_chunking import perform_hybrid_chunking
from app.temporal.activities.extraction import extract_section_fields
from app.temporal.activities import entity_resolution
from app.temporal.activities import indexing
from app.temporal.activities.stages import update_stage_status
from app.temporal.activities import policy_comparison_activities

from app.utils.logging import get_logger

logger = get_logger(__name__)


async def main():
    """Start the Temporal worker."""
    # Get Temporal host from environment (defaults to localhost for local development)
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    
    logger.info(f"Connecting to Temporal server at {temporal_host}")
    
    # Connect to Temporal server
    client = await Client.connect(
        target_host=temporal_host,
        namespace="default",
    )
    
    logger.info("Successfully connected to Temporal server")
    
    # Create single worker handling all activities
    worker = Worker(
        client,
        task_queue="documents-queue",
        workflows=[
            ProcessDocumentWorkflow,

            # Stages workflows
            ProcessedStageWorkflow,
            ExtractedStageWorkflow,
            EnrichedStageWorkflow,
            SummarizedStageWorkflow,

            # Child workflows
            OCRExtractionWorkflow,
            TableExtractionWorkflow,
            PageAnalysisWorkflow,
            HybridChunkingWorkflow,
            ExtractionWorkflow,
            EntityResolutionWorkflow,
            IndexingWorkflow,

            # Insurance business-specific workflows
            PolicyComparisonWorkflow,
        ],
        activities=[
            # OCR activities
            extract_ocr,
            extract_tables,
            
            # Page analysis activities
            page_analysis.extract_page_signals,
            page_analysis.extract_page_signals_from_markdown,
            page_analysis.classify_pages,
            page_analysis.create_page_manifest,

            # Hybrid chunking activity
            perform_hybrid_chunking,

            # Extraction activities
            extract_section_fields,

            # Entity resolution activities
            entity_resolution.aggregate_document_entities,
            entity_resolution.resolve_canonical_entities,
            entity_resolution.extract_relationships,
            entity_resolution.rollback_entities,

            # Indexing activities
            indexing.generate_embeddings_activity,
            indexing.construct_knowledge_graph_activity,

            # Stage update activity
            update_stage_status,

            # Insurance business-specific activities
            policy_comparison_activities.phase_a_preflight_activity,
            policy_comparison_activities.check_document_readiness_activity,
            policy_comparison_activities.phase_b_preflight_activity,
            policy_comparison_activities.section_alignment_activity,
            policy_comparison_activities.numeric_diff_activity,
            policy_comparison_activities.persist_comparison_result_activity,
        ],
        max_concurrent_activities=5,
        max_concurrent_workflow_tasks=10,
    )
    
    logger.info("=" * 60)
    logger.info("Temporal Worker Started Successfully")
    logger.info("=" * 60)
    logger.info(f"Connected to: {temporal_host}")
    logger.info(f"Task Queue: documents-queue")
    logger.info("=" * 60)
    logger.info("Worker is now polling for tasks...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    # Run the worker
    await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nWorker stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        raise
