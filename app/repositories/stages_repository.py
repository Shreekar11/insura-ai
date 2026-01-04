"""This repository is responsible for handling all the stages of the document processing pipeline."""

from sqlalchemy import select
from app.utils.logging import get_logger
from uuid import UUID
from fastapi import HTTPException

from app.database.session import async_session_maker
from app.repositories.base_repository import BaseRepository

LOGGER = get_logger(__name__)

from app.database.models import DocumentReadiness

class StagesRepository(BaseRepository[DocumentReadiness]):
    async def get_all_document_stages(self):
        try:
            async with async_session_maker() as session:
                query = select(DocumentReadiness)
                result = await session.execute(query)

                LOGGER.info("All document stages: %s", result.all())

                return result.all()
        except Exception as e:
            LOGGER.error("Failed to get all document stages", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    async def get_document_stage(self, document_id: UUID):
        try:
            async with async_session_maker() as session:
                query = select(DocumentReadiness).where(DocumentReadiness.document_id == document_id)
                result = await session.execute(query)

                return result.scalar_one_or_none()
        except Exception as e:
            LOGGER.error("Failed to get document stage", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
