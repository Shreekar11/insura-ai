import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, Set, Optional
from uuid import UUID

from sqlalchemy import select
from app.core.database import async_session_maker
from app.database.models import Workflow, WorkflowDocumentStageRun, WorkflowStageRun
from app.schemas.sse_schemas import SSEEvent, SSEEventType
from app.services.sse_messages import format_stage_message
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class SSEManager:
    """Manages SSE connections and event streaming for workflows."""
    
    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        # Track emitted events to avoid duplicates
        self._emitted_stage_runs: Set[str] = set()
        self._emitted_run_events: Set[str] = set()

    async def stream_workflow_events(
        self, 
        workflow_id: UUID
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events for a specific workflow."""
        last_check = datetime.now(timezone.utc)
        
        # Initial events (completed stages)
        async for event in self._get_initial_events(workflow_id):
            yield self._format_sse(event)

        # Initial run events
        async for event in self._get_initial_run_events(workflow_id):
            yield self._format_sse(event)

        try:
            while True:
                # 1. Heartbeat
                yield self._format_sse(SSEEvent(
                    event_type=SSEEventType.HEARTBEAT,
                    workflow_id=workflow_id,
                    data={"message": "keep-alive"}
                ))

                # 2. Check for updates
                async for event in self._poll_updates(workflow_id):
                    yield self._format_sse(event)

                # 3. Check for workflow completion
                is_finished, final_status = await self._is_workflow_finished(workflow_id)
                if is_finished:
                    event_type = (
                        SSEEventType.WORKFLOW_COMPLETED 
                        if final_status == "completed" 
                        else SSEEventType.WORKFLOW_FAILED
                    )
                    yield self._format_sse(SSEEvent(
                        event_type=event_type,
                        workflow_id=workflow_id,
                        data={"status": final_status, "message": f"Workflow {final_status}"}
                    ))
                    break

                await asyncio.sleep(self.poll_interval)
                
        except asyncio.CancelledError:
            LOGGER.info(f"SSE connection cancelled for workflow {workflow_id}")
        except Exception as e:
            LOGGER.error(f"Error in SSE stream for {workflow_id}: {e}", exc_info=True)
            yield self._format_sse(SSEEvent(
                event_type=SSEEventType.STAGE_FAILED,
                workflow_id=workflow_id,
                data={"message": f"Stream error: {str(e)}"}
            ))

    async def _get_initial_events(self, workflow_id: UUID) -> AsyncGenerator[SSEEvent, None]:
        """Yield events for already completed stages."""
        async with async_session_maker() as session:
            query = select(WorkflowDocumentStageRun).where(
                WorkflowDocumentStageRun.workflow_id == workflow_id
            ).order_by(WorkflowDocumentStageRun.started_at.asc())
            
            result = await session.execute(query)
            stages = result.scalars().all()
            
            for stage in stages:
                event = self._create_stage_event(workflow_id, stage)
                if event:
                    self._emitted_stage_runs.add(f"{stage.id}:{stage.status}")
                    yield event

    async def _poll_updates(self, workflow_id: UUID) -> AsyncGenerator[SSEEvent, None]:
        """Poll for new stage updates."""
        async with async_session_maker() as session:
            query = select(WorkflowDocumentStageRun).where(
                WorkflowDocumentStageRun.workflow_id == workflow_id
            )
            
            result = await session.execute(query)
            stages = result.scalars().all()
            
            for stage in stages:
                # Only emit if status changed or it's a new stage
                state_key = f"{stage.id}:{stage.status}"
                if state_key not in self._emitted_stage_runs:
                    event = self._create_stage_event(workflow_id, stage)
                    if event:
                        self._emitted_stage_runs.add(state_key)
                        yield event

        # Poll for run events (granular progress)
        async with async_session_maker() as session:
            from app.database.models import WorkflowRunEvent
            query = select(WorkflowRunEvent).where(
                WorkflowRunEvent.workflow_id == workflow_id
            ).order_by(WorkflowRunEvent.created_at.asc())
            
            result = await session.execute(query)
            run_events = result.scalars().all()
            
            for run_event in run_events:
                state_key = f"runevent:{run_event.id}"
                if state_key not in self._emitted_run_events:
                    yield SSEEvent(
                        event_type=SSEEventType.WORKFLOW_PROGRESS,
                        workflow_id=workflow_id,
                        timestamp=run_event.created_at,
                        data=run_event.event_payload or {}
                    )
                    self._emitted_run_events.add(state_key)

    async def _get_initial_run_events(self, workflow_id: UUID) -> AsyncGenerator[SSEEvent, None]:
        """Yield initial run events."""
        async with async_session_maker() as session:
            from app.database.models import WorkflowRunEvent
            query = select(WorkflowRunEvent).where(
                WorkflowRunEvent.workflow_id == workflow_id
            ).order_by(WorkflowRunEvent.created_at.asc())
            
            result = await session.execute(query)
            run_events = result.scalars().all()
            
            for run_event in run_events:
                state_key = f"runevent:{run_event.id}"
                yield SSEEvent(
                    event_type=SSEEventType.WORKFLOW_PROGRESS,
                    workflow_id=workflow_id,
                    timestamp=run_event.created_at,
                    data=run_event.event_payload or {}
                )
                self._emitted_run_events.add(state_key)

    def _create_stage_event(self, workflow_id: UUID, stage: WorkflowDocumentStageRun) -> Optional[SSEEvent]:
        """Create an SSEEvent from a WorkflowDocumentStageRun."""
        event_type = SSEEventType.STAGE_STARTED if stage.status == "running" else SSEEventType.STAGE_COMPLETED
        if stage.status == "failed":
            event_type = SSEEventType.STAGE_FAILED
            
        message = format_stage_message(stage.stage_name, stage.status, stage.stage_metadata)
        
        return SSEEvent(
            event_type=event_type,
            workflow_id=workflow_id,
            timestamp=stage.updated_at,
            data={
                "stage_name": stage.stage_name,
                "document_id": str(stage.document_id),
                "workflow_id": str(workflow_id),
                "status": stage.status,
                "message": message,
                "has_output": stage.stage_name == "extracted" and stage.status == "completed",
                "metadata": stage.stage_metadata
            }
        )

    async def _is_workflow_finished(self, workflow_id: UUID) -> tuple[bool, str]:
        """Check if the entire workflow has finished."""
        async with async_session_maker() as session:
            query = select(Workflow).where(Workflow.id == workflow_id)
            result = await session.execute(query)
            wf = result.scalar_one_or_none()
            if wf and wf.status in {"completed", "failed"}:
                return True, wf.status
            return False, ""

    def _format_sse(self, event: SSEEvent) -> str:
        """Format an SSEEvent as a raw SSE message."""
        data = event.model_dump(mode="json")
        return f"event: {data['event_type']}\ndata: {json.dumps(data)}\n\n"
