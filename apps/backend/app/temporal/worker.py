"""Temporal worker service for document processing.

This worker:
- Connects to local Temporal server (localhost:7233)
- Dynamically discovers and registers all workflows and activities
- Supports multiple task queues via separate workers
- Handles concurrent execution with configured limits
"""

import asyncio
import os
from typing import List
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions
from fastapi import FastAPI
import uvicorn
import httpx

from app.core.config import settings

# Trigger discovery of all components
from app.temporal.core.discovery import discover_all
discover_all()

from app.temporal.core.workflow_registry import WorkflowRegistry
from app.temporal.core.activity_registry import ActivityRegistry
from app.temporal.core.constants import DEFAULT_TASK_QUEUE
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Create a minimal FastAPI app for health checks
app = FastAPI(title="Temporal Worker Health Check")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "temporal-worker"}

@app.get("/")
async def root():
    return {"message": "Temporal Worker is running", "health": "/health"}

async def ping_health_endpoint():
    """Background task to ping the health endpoint every minute."""
    url = "https://insura-ai-worker.onrender.com/health"
    await asyncio.sleep(60)  # Wait for initial startup
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                logger.info(f"Pinging health endpoint: {url}")
                response = await client.get(url, timeout=10.0)
                logger.info(f"Health ping status: {response.status_code}")
            except Exception as e:
                logger.error(f"Health ping failed: {e}")
            
            await asyncio.sleep(60)

async def run_health_check_server():
    """Run the health check server."""
    port = int(os.getenv("PORT", 8001))
    logger.info(f"Starting health check server on port {port}")
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def run_workers():
    """Connect to Temporal and run workers with retries."""
    max_retries = 5
    retry_delay = 5
    client = None

    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to Temporal server at {settings.temporal_host}:{settings.temporal_port} (Attempt {attempt + 1}/{max_retries})")
            # Connect to Temporal server using centralized settings
            client = await Client.connect(
                target_host=f"{settings.temporal_host}:{settings.temporal_port}",
                namespace=settings.temporal_namespace,
            )
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}. Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect to Temporal server after {max_retries} attempts: {e}")
                raise
            
    logger.info("Successfully connected to Temporal server")
    
    # Get all registered workflows and activities
    all_workflows = WorkflowRegistry.get_all_workflows()
    all_activities = ActivityRegistry.get_all_activities()
    
    logger.info(f"Registered {len(all_workflows)} workflows and {len(all_activities)} activities")
    
    # Group workflows by task queue
    queues = {}
    for wf_name, metadata in all_workflows.items():
        queue = metadata.task_queue or DEFAULT_TASK_QUEUE
        if queue not in queues:
            queues[queue] = []
        queues[queue].append(metadata.workflow_class)
        logger.debug(f"Workflow '{wf_name}' assigned to queue '{queue}'")

    # Create workers for each task queue
    workers = []
    for queue_name, workflows in queues.items():
        logger.debug(f"Starting worker for queue: {queue_name} (Workflows: {[w.__name__ for w in workflows]})")
        
        # All activities are registered with all workers for now
        # In a more complex setup, you might filter activities by queue as well
        worker = Worker(
            client,
            task_queue=queue_name,
            workflows=workflows,
            activities=list(all_activities.values()),
            max_concurrent_activities=10,
            max_concurrent_workflow_tasks=20,
            workflow_runner=SandboxedWorkflowRunner(
                restrictions=SandboxRestrictions.default.with_passthrough_all_modules()
            ),
        )
        workers.append(worker.run())

    logger.info("=" * 60)
    logger.info("Temporal Workers Initialized Successfully")
    logger.info("=" * 60)
    logger.info(f"Connected to: {settings.temporal_host}:{settings.temporal_port}")
    logger.info(f"Queues: {list(queues.keys())}")
    logger.info("=" * 60)
    logger.info("Workers are now polling for tasks...")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)
    
    # Run all workers
    await asyncio.gather(*workers)


async def main():
    """Start the Temporal worker(s)."""
    logger.info(f"Connecting to Temporal server at {settings.temporal_host}:{settings.temporal_port}")
    
    # Run health check server, workers, and keep-alive ping concurrently
    # The health check server binds to the port immediately, satisfying Render's requirements
    await asyncio.gather(
        run_health_check_server(), 
        run_workers(),
        ping_health_endpoint()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nWorkers stopped by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        raise
