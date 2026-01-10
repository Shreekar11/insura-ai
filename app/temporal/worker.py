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

# Import all activities
from app.temporal.activities.ocr_extraction import (
    extract_ocr,
)
from app.temporal.activities.table_extraction import (
    extract_tables,
)
from app.temporal.activities.page_analysis import (
    extract_page_signals,
    extract_page_signals_from_markdown,
    classify_pages,
    create_page_manifest,
)
from app.temporal.activities.hybrid_chunking import (
    perform_hybrid_chunking,
)
from app.temporal.activities.extraction import (
    extract_section_fields,
)
from app.temporal.activities.entity_resolution import (
    aggregate_document_entities,
    resolve_canonical_entities,
    extract_relationships,
    rollback_entities,
)
from app.temporal.activities.indexing import (
    generate_embeddings_activity,
    construct_knowledge_graph_activity,
)
from app.temporal.activities.stages import (
    update_stage_status,
)

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
            ProcessedStageWorkflow,
            ExtractedStageWorkflow,
            EnrichedStageWorkflow,
            SummarizedStageWorkflow,
            OCRExtractionWorkflow,
            TableExtractionWorkflow,
            PageAnalysisWorkflow,
            HybridChunkingWorkflow,
            ExtractionWorkflow,
            EntityResolutionWorkflow,
            IndexingWorkflow,
        ],
        activities=[
            extract_ocr,
            extract_tables,
            extract_page_signals,
            extract_page_signals_from_markdown,
            classify_pages,
            create_page_manifest,
            perform_hybrid_chunking,
            extract_section_fields,
            aggregate_document_entities,
            resolve_canonical_entities,
            extract_relationships,
            rollback_entities,
            generate_embeddings_activity,
            construct_knowledge_graph_activity,
            update_stage_status,
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
