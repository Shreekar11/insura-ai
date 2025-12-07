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

# Import all workflows
from app.temporal.workflows.process_document import ProcessDocumentWorkflow
from app.temporal.workflows.ocr_extraction import OCRExtractionWorkflow
from app.temporal.workflows.normalization import NormalizationWorkflow
from app.temporal.workflows.entity_resolution import EntityResolutionWorkflow

# Import all activities
from app.temporal.activities.ocr_activities import (
    extract_ocr,
)
from app.temporal.activities.normalization_activities import (
    normalize_and_classify_document,
)
from app.temporal.activities.entity_activities import (
    aggregate_document_entities,
    resolve_canonical_entities,
    extract_relationships,
    rollback_entities,
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
            OCRExtractionWorkflow,
            NormalizationWorkflow,
            EntityResolutionWorkflow,
        ],
        activities=[
            extract_ocr,
            normalize_and_classify_document,
            aggregate_document_entities,
            resolve_canonical_entities,
            extract_relationships,
            rollback_entities,
        ],
        max_concurrent_activities=5,
        max_concurrent_workflow_tasks=10,
    )
    
    logger.info("=" * 60)
    logger.info("Temporal Worker Started Successfully")
    logger.info("=" * 60)
    logger.info(f"Connected to: {temporal_host}")
    logger.info(f"Task Queue: documents-queue")
    logger.info(f"Max Concurrent Activities: 5")
    logger.info(f"Max Concurrent Workflow Tasks: 10")
    logger.info(f"Registered Workflows: 4")
    logger.info(f"Registered Activities: 7")
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
