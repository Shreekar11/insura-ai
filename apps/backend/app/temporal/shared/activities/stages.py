"""Temporal activities for stage management."""

from uuid import UUID
from temporalio import activity
from typing import Optional
from app.core.database import async_session_maker
from app.repositories.stages_repository import StagesRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.repositories.document_repository import DocumentRepository
from app.services.sse_messages import format_stage_message
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
    error_message: Optional[str] = None,
    stage_metadata: Optional[dict] = None
) -> bool:
    """Updates the completion status of a processing stage."""
    async with async_session_maker() as session:
        stage_repo = StagesRepository(session)
        result = await stage_repo.update_stage_status(
            document_id=document_id,
            workflow_id=workflow_id,
            stage_name=stage_name,
            status=status,
            error_message=error_message,
            stage_metadata=stage_metadata
        )

        # Update document status
        doc_repo = DocumentRepository(session)
        
        # Status mapping for documents
        status_map = {
            ("processed", "running"): "ocr_processing",
            ("processed", "completed"): "ocr_completed",
            ("classified", "running"): "classifying",
            ("classified", "completed"): "classified",
            ("extracted", "running"): "extracting",
            ("extracted", "completed"): "extracted",
            ("summarized", "running"): "indexing",
            ("summarized", "completed"): "completed",
        }
        
        doc_status = status_map.get((stage_name, status))
        if status == "failed":
            doc_status = "failed"
            
        if doc_status:
            await doc_repo.update_status(UUID(document_id), doc_status)

        # Persist a granular event so historical runs/completed streams can show the timeline + output
        wf_repo = WorkflowRepository(session)
        payload = {
            "stage_name": stage_name,
            "status": status,
            "document_id": document_id,
            "workflow_id": workflow_id,
            "message": format_stage_message(stage_name, status, stage_metadata),
            "has_output": stage_name == "extracted" and status == "completed",
            "metadata": stage_metadata
        }
        await wf_repo.emit_run_event(
            workflow_id=UUID(workflow_id),
            event_type="workflow:progress",
            payload=payload
        )

        await session.commit()
        return result


@ActivityRegistry.register("shared", "emit_workflow_event")
@activity.defn
async def emit_workflow_event(
    workflow_id: str,
    event_type: str,
    payload: Optional[dict] = None
) -> bool:
    """Emits a granular workflow event for SSE streaming.
    
    Args:
        workflow_id: UUID of the workflow
        event_type: Type of event (e.g. "workflow:progress")
        payload: Optional JSON payload
        
    Returns:
        True if the event was persisted successfully
    """
    async with async_session_maker() as session:
        wf_repo = WorkflowRepository(session)
        await wf_repo.emit_run_event(
            workflow_id=UUID(workflow_id),
            event_type=event_type,
            payload=payload
        )
        await session.commit()
        return True


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
