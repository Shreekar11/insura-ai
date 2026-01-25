"""Temporal activities for stage management."""

from uuid import UUID
from temporalio import activity
from typing import Optional
from app.core.database import async_session_maker
from app.repositories.stages_repository import StagesRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry

LOGGER = get_logger(__name__)


@ActivityRegistry.register("shared", "update_workflow_status")
@activity.defn
async def update_workflow_status(
    workflow_id: str,
    status: str  # "completed" | "failed"
) -> bool:
    """Update workflow status in the database.
    
    This activity should be called at the end of workflow execution
    to persist the final status to the database.
    
    Args:
        workflow_id: UUID of the workflow to update (as string)
        status: New status value ("completed" or "failed")
        
    Returns:
        True if update was successful
    """
    LOGGER.info(f"Updating workflow {workflow_id} status to: {status}")
    async with async_session_maker() as session:
        wf_repo = WorkflowRepository(session)
        await wf_repo.update_status(
            workflow_id=UUID(workflow_id),
            status=status
        )
        await session.commit()
        LOGGER.info(f"Workflow {workflow_id} status updated to: {status}")
        return True


@ActivityRegistry.register("shared", "update_stage_status")
@activity.defn
async def update_stage_status(
    workflow_id: str,
    document_id: str,
    stage_name: str,
    status: str,  # running | completed | failed
    error_message: Optional[str] = None
) -> bool:
    """Updates the completion status of a processing stage."""
    async with async_session_maker() as session:
        stage_repo = StagesRepository(session)
        result = await stage_repo.update_stage_status(
            document_id=document_id,
            workflow_id=workflow_id,
            stage_name=stage_name,
            status=status,
            error_message=error_message
        )
        await session.commit()
        return result


@ActivityRegistry.register("shared", "check_stage_readiness")
@activity.defn
async def check_stage_readiness(workflow_id: str, document_id: str) -> dict:
    """Checks the readiness status of all stages."""
    async with async_session_maker() as session:
        stage_repo = StagesRepository(session)
        runs = await stage_repo.get_document_stage(document_id=UUID(document_id), workflow_id=UUID(workflow_id))
        status_map = {run.stage_name: run.status == "completed" for run in runs}
        return {
            "processed": status_map.get("processed", False),
            "classified": status_map.get("classified", False),
            "extracted": status_map.get("extracted", False),
            "enriched": status_map.get("enriched", False),
            "summarized": status_map.get("summarized", False)
        }
