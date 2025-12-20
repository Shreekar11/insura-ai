"""OCR activities for Phase 1.

These activities extract raw text using the OCR pipeline.
"""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID
import time

from app.database.base import async_session_maker
from app.pipeline.ocr_extraction import OCRExtractionPipeline
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_ocr(document_id: str, pages_to_process: Optional[List[int]] = None) -> Dict:
    """Extract OCR text from document and persist pages to database."""
    start = time.time()
    
    try:
        activity.logger.info(f"[Phase 1: OCR Extraction] Starting OCR extraction for document: {document_id}")
        
        async with async_session_maker() as session:
            # Get document URL
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_path:
                raise ValueError(f"Document {document_id} not found or has no file path")
            
            pipeline = OCRExtractionPipeline(session)
            pages = await pipeline.extract_and_store_pages(UUID(document_id), document.file_path)
            
            await session.commit()
            
            activity.logger.info(f"[Phase 1: OCR Extraction] OCR extraction complete: {len(pages)} pages extracted")
        
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
