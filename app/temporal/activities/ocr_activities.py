"""OCR activities that wrap the existing OCRService.

These activities provide Temporal-compatible wrappers around:
- app/services/ocr/ocr_service.py
"""

from temporalio import activity
from typing import Dict
from uuid import UUID
import time

from app.services.ocr.ocr_service import OCRService
from app.repositories.ocr_repository import OCRRepository
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
        
        # Get document URL from database
        from app.database.session import get_session
        async with get_session() as session:
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_url:
                raise ValueError(f"Document {document_id} not found or has no file URL")
            
            document_url = document.file_url
        
        # Use existing OCR service
        async with get_session() as session:
            ocr_service = OCRService(db_session=session)
            result = await ocr_service.run(
                document_url=document_url,
                document_id=UUID(document_id)
            )
        
        activity.logger.info(
            f"OCR extraction complete for {document_id}: "
            f"{len(result.get('pages', []))} pages extracted"
        )
        
        return result
        
    except Exception as e:
        activity.logger.error(f"OCR extraction failed for {document_id}: {e}")
        raise
    finally:
        duration = time.time() - start
        activity.logger.info(f"OCR extraction duration: {duration:.2f}s")


@activity.defn
async def store_ocr_results(document_id: str, ocr_data: Dict) -> None:
    """
    Store OCR results in database.
    
    Args:
        document_id: UUID of the document
        ocr_data: OCR extraction results with pages
    """
    try:
        activity.logger.info(f"Storing OCR results for document: {document_id}")
        
        from app.database.session import get_session
        async with get_session() as session:
            ocr_repo = OCRRepository(session)
            
            # Store OCR pages
            pages = ocr_data.get('pages', [])
            if pages:
                await ocr_repo.store_ocr_pages(UUID(document_id), pages)
                activity.logger.info(f"Stored {len(pages)} OCR pages for {document_id}")
            else:
                activity.logger.warning(f"No pages to store for {document_id}")
        
    except Exception as e:
        activity.logger.error(f"Failed to store OCR results for {document_id}: {e}")
        raise
