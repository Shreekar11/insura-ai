"""OCR activities that wrap the existing OCRService.

These activities provide Temporal-compatible wrappers around:
- app/services/ocr/ocr_service.py
"""

from temporalio import activity
from typing import Dict
from uuid import UUID
import time

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_ocr(document_id: str) -> Dict:
    """
    Extract OCR text from document and persist pages to database.
    
    This activity only performs OCR extraction using Mistral API.
    It does NOT perform normalization, classification, or entity extraction.
    
    Args:
        document_id: UUID of the document to process
        
    Returns:
        Dictionary with document_id and page_count
    """
    start = time.time()
    
    try:
        activity.logger.info(f"Starting OCR extraction for document: {document_id}")
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from app.repositories.document_repository import DocumentRepository
        from app.services.ocr.ocr_service import OCRService
        from app.config import settings
        
        # Get document URL from database
        async with async_session_maker() as session:
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_path:
                raise ValueError(f"Document {document_id} not found or has no file path")
            
            document_url = document.file_path
            activity.logger.info(f"Retrieved document URL for {document_id}")
        
        # Extract raw text using OCR service
        async with async_session_maker() as session:
            ocr_service = OCRService(
                api_key=settings.mistral_api_key,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                db_session=session,
                provider=settings.llm_provider,
                openrouter_api_key=settings.openrouter_api_key if settings.llm_provider == "openrouter" else None,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
            )
            
            # Extract raw text only
            pages = await ocr_service.extract_text_only(
                document_url=document_url,
                document_id=UUID(document_id)
            )
            
            activity.logger.info(f"OCR extraction complete: {len(pages)} pages extracted")
        
        # Store pages in database using DocumentRepository
        async with async_session_maker() as session:
            doc_repo = DocumentRepository(session)
            await doc_repo.store_pages(UUID(document_id), pages)
            await session.commit()
            
            activity.logger.info(f"Stored {len(pages)} pages for document {document_id}")
        
        return {
            "document_id": document_id,
            "page_count": len(pages),
        }
        
    except Exception as e:
        activity.logger.error(f"OCR extraction failed for {document_id}: {e}")
        raise
    finally:
        duration = time.time() - start
        activity.logger.info(f"OCR extraction duration: {duration:.2f}s")
