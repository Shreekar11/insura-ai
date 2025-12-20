"""Phase 1: OCR Extraction facade.

Wraps OCRService for raw text extraction.
"""

from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ocr.ocr_service import OCRService
from app.repositories.document_repository import DocumentRepository
from app.models.page_data import PageData
from app.config import settings
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class OCRExtractionPipeline:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.ocr_service = OCRService(
            api_key=settings.mistral_api_key,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            db_session=session,
            provider=settings.llm_provider,
            openrouter_api_key=settings.openrouter_api_key if settings.llm_provider == "openrouter" else None,
            openrouter_api_url=settings.openrouter_api_url,
            openrouter_model=settings.openrouter_model,
        )

    async def extract_and_store_pages(self, document_id: UUID, document_url: str) -> List[PageData]:
        """Extract raw text and store in database."""
        # Extract raw text only
        pages = await self.ocr_service.extract_text_only(
            document_url=document_url,
            document_id=document_id
        )
        
        # Store in database
        await self.doc_repo.store_pages(document_id, pages)
        
        return pages

