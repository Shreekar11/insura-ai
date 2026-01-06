"""
This repository is responsible for handling all the stages of the document
processing pipeline.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base_repository import BaseRepository
from app.database.models import (
    WorkflowDocumentStageRun,
    WorkflowStageRun,
    WorkflowDocument,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class StagesRepository(BaseRepository[WorkflowDocumentStageRun]):
    def __init__(self, session: AsyncSession):
        """
        Initialize stages repository.

        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, WorkflowDocumentStageRun)
        self.session = session

    @staticmethod
    def _serialize_stage(stage: WorkflowDocumentStageRun) -> dict:
        """Serialize WorkflowDocumentStageRun ORM object to dict."""
        return {
            "id": stage.id,
            "document_id": stage.document_id,
            "workflow_id": stage.workflow_id,
            "stage_name": stage.stage_name,
            "status": stage.status,
            "started_at": stage.started_at,
            "completed_at": stage.completed_at,
            "error_message": stage.error_message,
        }

    async def get_all_document_stages(self) -> List[dict]:
        """Fetch all document-stage runs."""
        try:
            query = select(WorkflowDocumentStageRun)
            result = await self.session.execute(query)
            stages = result.scalars().all()

            serialized = [self._serialize_stage(stage) for stage in stages]

            LOGGER.info(
                "[StagesRepository] Retrieved all document stages",
                extra={"count": len(serialized)},
            )

            return serialized

        except Exception:
            LOGGER.error("Failed to get all document stages", exc_info=True)
            raise

    async def get_document_stage(
        self,
        document_id: UUID,
        workflow_id: UUID,
    ) -> List[dict]:
        """Fetch all stages for a given document and workflow."""
        try:
            query = select(WorkflowDocumentStageRun).where(
                WorkflowDocumentStageRun.document_id == document_id,
                WorkflowDocumentStageRun.workflow_id == workflow_id,
            )

            result = await self.session.execute(query)
            stages = result.scalars().all()

            serialized = [self._serialize_stage(stage) for stage in stages]

            return serialized

        except Exception:
            LOGGER.error(
                "Failed to get document stage",
                exc_info=True,
                extra={
                    "document_id": str(document_id),
                    "workflow_id": str(workflow_id),
                },
            )
            raise

    async def update_stage_status(
        self,
        document_id: UUID,
        workflow_id: UUID,
        stage_name: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update document-level stage status and aggregate to workflow-level.
        """
        now = datetime.now(timezone.utc)

        query = select(WorkflowDocumentStageRun).where(
            WorkflowDocumentStageRun.document_id == document_id,
            WorkflowDocumentStageRun.workflow_id == workflow_id,
            WorkflowDocumentStageRun.stage_name == stage_name,
        )

        result = await self.session.execute(query)
        stage_run = result.scalar_one_or_none()

        if not stage_run:
            stage_run = WorkflowDocumentStageRun(
                document_id=document_id,
                workflow_id=workflow_id,
                stage_name=stage_name,
                status=status,
                started_at=now,
                completed_at=now if status in {"completed", "failed"} else None,
                error_message=error_message,
            )
            self.session.add(stage_run)
        else:
            stage_run.status = status
            if status in {"completed", "failed"}:
                stage_run.completed_at = now
            if error_message:
                stage_run.error_message = error_message

        await self.session.flush()

        doc_query = select(WorkflowDocument).where(
            WorkflowDocument.workflow_id == workflow_id,
            WorkflowDocument.document_id == document_id,
        )
        doc_result = await self.session.execute(doc_query)
        total_docs = len(doc_result.scalars().all())

        status_query = select(WorkflowDocumentStageRun.status).where(
            WorkflowDocumentStageRun.workflow_id == workflow_id,
            WorkflowDocumentStageRun.stage_name == stage_name,
        )
        status_result = await self.session.execute(status_query)
        statuses = status_result.scalars().all()

        completed_count = sum(1 for s in statuses if s == "completed")
        failed_count = sum(1 for s in statuses if s == "failed")

        wf_stage_query = (
            select(WorkflowStageRun)
            .where(
                WorkflowStageRun.workflow_id == workflow_id,
                WorkflowStageRun.stage_name == stage_name,
            )
            .with_for_update()
        )
        wf_stage_result = await self.session.execute(wf_stage_query)
        wf_stage = wf_stage_result.scalar_one_or_none()

        if not wf_stage:
            wf_stage = WorkflowStageRun(
                workflow_id=workflow_id,
                stage_name=stage_name,
                status="running",
                started_at=now,
            )
            self.session.add(wf_stage)

        if completed_count == total_docs and total_docs > 0:
            wf_stage.status = "completed"
            wf_stage.completed_at = now
        elif (completed_count + failed_count) == total_docs and failed_count > 0:
            wf_stage.status = "partial"
            wf_stage.completed_at = now
        else:
            wf_stage.status = "running"

        await self.session.flush()
        return True
