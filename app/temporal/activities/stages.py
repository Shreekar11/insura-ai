"""Temporal activities for stage management."""

from datetime import datetime
from uuid import UUID
from temporalio import activity
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.session import async_session_maker
from app.repositories.stages_repository import StagesRepository


@activity.defn
async def update_stage_status(
    document_id: str,
    stage_name: str,
    status: str,  # running | completed | failed
    workflow_id: str,
    error_message: Optional[str] = None
) -> bool:
    """Updates the completion status of a processing stage for a document and aggregates workflow status."""
    activity.logger.info(f"Updating stage {stage_name} for doc {document_id} in workflow {workflow_id} to {status}")
    
    doc_uuid = UUID(document_id)
    wf_uuid = UUID(workflow_id)
    
    async with async_session_maker() as session:
        stage_repo = StagesRepository(session)
        result = await stage_repo.update_stage_status(
            document_id=doc_uuid,
            workflow_id=wf_uuid,
            stage_name=stage_name,
            status=status,
            error_message=error_message
        )
        await session.commit()
        return result


@activity.defn
async def check_stage_readiness(document_id: str, workflow_id: str) -> dict:
    """Checks the readiness status of all stages for a document in a specific workflow."""
    doc_uuid = UUID(document_id)
    wf_uuid = UUID(workflow_id)
    
    async with async_session_maker() as session:
        stage_repo = StagesRepository(session)
        runs = await stage_repo.get_document_stage(doc_uuid, wf_uuid)
        
        status_map = {run.stage_name: run.status == "completed" for run in runs}
        
        return {
            "processed": status_map.get("processed", False),
            "classified": status_map.get("classified", False),
            "extracted": status_map.get("extracted", False),
            "enriched": status_map.get("enriched", False),
            "summarized": status_map.get("summarized", False)
        }
