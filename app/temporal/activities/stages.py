"""Temporal activities for stage management."""

from datetime import datetime
from uuid import UUID
from temporalio import activity
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.session import async_session_maker
from app.database.models import DocumentReadiness


@activity.defn
async def update_stage_status(
    document_id: str,
    stage_name: str,
    is_complete: bool
) -> bool:
    """Updates the completion status of a processing stage."""
    activity.logger.info(f"Updating stage {stage_name} for {document_id} to {is_complete}")
    
    db_id = UUID(document_id)
    async with async_session_maker() as session:
        query = select(DocumentReadiness).where(DocumentReadiness.document_id == db_id)
        result = await session.execute(query)

        readiness = result.scalar_one_or_none()
        
        if not readiness:
            readiness = DocumentReadiness(document_id=db_id)
            session.add(readiness)
        
        # Set stage flag and timestamp
        field_name = stage_name.lower()
        if hasattr(readiness, field_name):
            setattr(readiness, field_name, is_complete)
            if is_complete:
                setattr(readiness, f"{field_name}_at", datetime.utcnow())
            
            await session.commit()
            return True
        
        return False


@activity.defn
async def check_stage_readiness(document_id: str) -> dict:
    """Checks the readiness status of all stages for a document."""
    db_id = UUID(document_id)
    async with async_session_maker() as session:
        query = select(DocumentReadiness).where(DocumentReadiness.document_id == db_id)
        result = await session.execute(query)
        readiness = result.scalar_one_or_none()
        
        if not readiness:
            return {
                "processed": False,
                "classified": False,
                "extracted": False,
                "enriched": False,
                "summarized": False
            }
        
        return {
            "processed": readiness.processed,
            "classified": readiness.classified,
            "extracted": readiness.extracted,
            "enriched": readiness.enriched,
            "summarized": readiness.summarized
        }
