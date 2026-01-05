"""This repository is responsible for handling all the stages of the document processing pipeline."""

from sqlalchemy import select
from app.utils.logging import get_logger
from uuid import UUID
from fastapi import HTTPException
from typing import Optional

from app.database.session import async_session_maker
from app.repositories.base_repository import BaseRepository

LOGGER = get_logger(__name__)

from app.database.models import WorkflowDocumentStageRun, WorkflowStageRun, WorkflowDocument
from datetime import datetime, timezone

class StagesRepository(BaseRepository[WorkflowDocumentStageRun]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, WorkflowDocumentStageRun)

    async def get_all_document_stages(self):
        try:
            query = select(WorkflowDocumentStageRun)
            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            LOGGER.error("Failed to get all document stages", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_document_stage(self, document_id: UUID, workflow_id: Optional[UUID] = None):
        try:
            query = select(WorkflowDocumentStageRun).where(WorkflowDocumentStageRun.document_id == document_id)
            if workflow_id:
                query = query.where(WorkflowDocumentStageRun.workflow_id == workflow_id)
            
            result = await self.session.execute(query)
            return result.scalars().all()
        except Exception as e:
            LOGGER.error("Failed to get document stage", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def update_stage_status(
        self,
        document_id: UUID,
        workflow_id: UUID,
        stage_name: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """Update document-level stage status and aggregate to workflow-level."""
        # 1. Update/Create Document Stage Run
        query = select(WorkflowDocumentStageRun).where(
            WorkflowDocumentStageRun.document_id == document_id,
            WorkflowDocumentStageRun.workflow_id == workflow_id,
            WorkflowDocumentStageRun.stage_name == stage_name
        )
        result = await self.session.execute(query)
        stage_run = result.scalar_one_or_none()
        
        if not stage_run:
            stage_run = WorkflowDocumentStageRun(
                document_id=document_id,
                workflow_id=workflow_id,
                stage_name=stage_name,
                status=status,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc) if status in ["completed", "failed"] else None,
                error_message=error_message
            )
            self.session.add(stage_run)
        else:
            stage_run.status = status
            if status in ["completed", "failed"]:
                stage_run.completed_at = datetime.now(timezone.utc)
            if error_message:
                stage_run.error_message = error_message
        
        await self.session.flush()

        # 2. Aggregate to Workflow Stage Run
        # Get total documents in workflow
        doc_query = select(WorkflowDocument).where(WorkflowDocument.workflow_id == workflow_id)
        doc_result = await self.session.execute(doc_query)
        total_docs = len(doc_result.scalars().all())

        # Get status counts
        status_query = select(WorkflowDocumentStageRun.status).where(
            WorkflowDocumentStageRun.workflow_id == workflow_id,
            WorkflowDocumentStageRun.stage_name == stage_name
        )
        status_result = await self.session.execute(status_query)
        statuses = status_result.scalars().all()
        
        completed_count = sum(1 for s in statuses if s == "completed")
        failed_count = sum(1 for s in statuses if s == "failed")

        # Update WorkflowStageRun
        wf_stage_query = select(WorkflowStageRun).where(
            WorkflowStageRun.workflow_id == workflow_id,
            WorkflowStageRun.stage_name == stage_name
        ).with_for_update()
        wf_stage_result = await self.session.execute(wf_stage_query)
        wf_stage = wf_stage_result.scalar_one_or_none()

        if not wf_stage:
            wf_stage = WorkflowStageRun(
                workflow_id=workflow_id,
                stage_name=stage_name,
                status="running",
                started_at=datetime.now(timezone.utc)
            )
            self.session.add(wf_stage)

        if completed_count == total_docs:
            wf_stage.status = "completed"
            wf_stage.completed_at = datetime.now(timezone.utc)
        elif (completed_count + failed_count) == total_docs and failed_count > 0:
            wf_stage.status = "partial"
            wf_stage.completed_at = datetime.now(timezone.utc)
        else:
            wf_stage.status = "running"

        await self.session.flush()
        return True
