"""OCR activities for OCR Extraction.

These activities extract raw text using the Docling-backed OCR pipeline.
Now accepts page_section_map from manifest to store page_type metadata
with each extracted page, enabling section-aware downstream processing.
"""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID
import time

from app.core.database import async_session_maker
from app.pipeline.ocr_extraction import OCRExtractionPipeline
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_ocr(
    workflow_id: str,
    document_id: str, 
) -> Dict:
    """Extract OCR text from document and persist pages to database.
    
    Args:
        document_id: UUID string of the document to process
    
    Returns:
        Dict containing:
            - document_id: The document ID
            - page_count: Number of pages processed
            - pages_processed: List of page numbers that were processed
    """
    start = time.time()
    
    try:
        activity.logger.info(
            f"[Phase 2: Full OCR] Starting OCR extraction for all pages "
            f"of document: {document_id}",
            extra={
                "document_id": document_id,
            }
        )
        
        async with async_session_maker() as session:
            # Get document URL
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_path:
                raise ValueError(f"Document {document_id} not found or has no file path")
            
            # Create pipeline and extract pages
            pipeline = OCRExtractionPipeline(session)
            
            # Pass pages_to_process and page_section_map to the pipeline
            pages = await pipeline.extract_and_store_pages(
                document_id=UUID(document_id),
                document_url=document.file_path,
            )
            
            await session.commit()
            
            pages_processed = [p.page_number for p in pages]
            
            activity.logger.info(
                f"[Phase 2: OCR Extraction] Complete: {len(pages)} pages extracted",
                extra={
                    "document_id": document_id,
                    "pages_processed": pages_processed,
                }
            )
        
        return {
            "document_id": document_id,
            "page_count": len(pages),
            "pages_processed": pages_processed,
        }
        
    except Exception as e:
        activity.logger.error(
            f"OCR extraction failed for {document_id}: {e}",
            extra={
                "document_id": document_id,
                "error_type": type(e).__name__
            }
        )
        raise
    finally:
        duration = time.time() - start
        activity.logger.info(
            f"OCR extraction duration: {duration:.2f}s",
            extra={"document_id": document_id, "duration_seconds": duration}
        )
