"""OCR activities for OCR Extraction."""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID
import time

from app.core.database import async_session_maker
from app.pipeline.ocr_extraction import OCRExtractionPipeline
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry

logger = get_logger(__name__)


@ActivityRegistry.register("shared", "extract_ocr")
@activity.defn
async def extract_ocr(
    workflow_id: str,
    document_id: str, 
) -> Dict:
    """Extract OCR text from document and persist pages to database."""
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
            
            pages_processed = [int(p.page_number) for p in pages]
            markdown_pages = [(p.markdown, int(p.page_number), p.metadata) for p in pages]
            
            activity.logger.info(
                "OCR Extraction Complete",
                extra={
                    "document_id": document_id,
                    "pages_processed": pages_processed,
                    "markdown_pages": markdown_pages,
                }
            )
        
        return {
            "document_id": document_id,
            "page_count": len(pages),
            "pages_processed": pages_processed,
            "markdown_pages": markdown_pages,
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
