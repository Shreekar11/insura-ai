"""API routes for document processing stages."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import async_session_maker
from app.database.models import DocumentReadiness
from sqlalchemy import select
from app.utils.logging import get_logger
from app.repositories.stages_repository import StagesRepository

LOGGER = get_logger(__name__)


router = APIRouter()

@router.get("/")
async def get_all_document_stages():
    """Get the completion status of all processing stages for all documents."""

    try: 
        stage_repo = StagesRepository()
        return await stage_repo.get_all_document_stages()
    except Exception as e:
        LOGGER.error("Failed to get all document stages", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}")
async def get_document_stages(
    document_id: uuid.UUID,
):
    """Get the completion status of all processing stages for a document."""

    try:
        stage_repo = StagesRepository()
        return await stage_repo.get_document_stage(document_id)
    except Exception as e:
        LOGGER.error("Failed to get document stages", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
    query = select(DocumentReadiness).where(DocumentReadiness.document_id == document_id)
    readiness = await session.execute(query).scalar_one_or_none()
    
    if not readiness:
        return {
            "document_id": document_id,
            "processed": False,
            "classified": False,
            "extracted": False,
            "enriched": False,
            "summarized": False
        }
    
    return {
        "document_id": document_id,
        "processed": readiness.processed,
        "processed_at": readiness.processed_at,
        "classified": readiness.classified,
        "classified_at": readiness.classified_at,
        "extracted": readiness.extracted,
        "extracted_at": readiness.extracted_at,
        "enriched": readiness.enriched,
        "enriched_at": readiness.enriched_at,
        "summarized": readiness.summarized,
        "summarized_at": readiness.summarized_at
    }
