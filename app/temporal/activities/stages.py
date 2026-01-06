"""Temporal activities for stage management."""

from uuid import UUID
from temporalio import activity
from typing import Optional

from app.core.database import async_session_maker
from app.repositories.stages_repository import StagesRepository

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

@activity.defn
async def update_stage_status(
    workflow_id: str,
    document_id: str,
    stage_name: str,
    status: str,  # running | completed | failed
    error_message: Optional[str] = None
) -> bool:
    """Updates the completion status of a processing stage for a document and aggregates workflow status."""
    
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


@activity.defn
async def check_stage_readiness(workflow_id: str, document_id: str) -> dict:
    """Checks the readiness status of all stages for a document in a specific workflow."""
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
