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
    Extract OCR data from document using existing OCRService.
    
    Args:
        document_id: UUID of the document to process
        
    Returns:
        Dictionary with OCR extraction results including pages
    """
    start = time.time()
    
    try:
        activity.logger.info(f"Starting OCR extraction for document: {document_id}")
        
        # Import inside function to avoid sandbox issues
        from app.database.base import async_session_maker
        from app.repositories.document_repository import DocumentRepository
        from app.services.ocr.ocr_service import OCRService
        
        # Get document URL from database
        async with async_session_maker() as session:
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_path:
                raise ValueError(f"Document {document_id} not found or has no file path")
            
            document_url = document.file_path
        
        # Use existing OCR service with required API keys
        async with async_session_maker() as session:
            ocr_service = OCRService(
                api_key=settings.mistral_api_key,
                gemini_api_key=settings.gemini_api_key,
                gemini_model=settings.gemini_model,
                db_session=session,
                provider=settings.llm_provider,
                openrouter_api_key=settings.openrouter_api_key,
                openrouter_api_url=settings.openrouter_api_url,
                openrouter_model=settings.openrouter_model,
            )
            result = await ocr_service.run(
                document_url=document_url,
                document_id=UUID(document_id)
            )
            
            # Convert OCRResult object to dict for serialization
            result_dict = result.to_dict()
        
        activity.logger.info(
            f"OCR extraction complete for {document_id}: "
            f"text length = {len(result_dict.get('text', ''))}"
        )
        
        return result_dict
        
    except Exception as e:
        activity.logger.error(f"OCR extraction failed for {document_id}: {e}")
        raise
    finally:
        duration = time.time() - start
        activity.logger.info(f"OCR extraction duration: {duration:.2f}s")
