"""OCR activities for OCR Extraction."""

from temporalio import activity
from typing import Dict, List, Optional
from uuid import UUID
import time

from app.core.database import async_session_maker
from app.pipeline.ocr_extraction import OCRExtractionPipeline
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry
from app.services.storage_service import StorageService

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

            # Load PDF bytes for coordinate extraction (enables page dimensions)
            pdf_bytes = None
            
            # Use signed URL for storage access (bucket "docs" is private)
            storage_service = StorageService()
            document_url = await storage_service.create_download_url(
                bucket="docs",
                path=document.file_path,
                expires_in=3600 # 1 hour for extraction
            )
            
            try:
                # Download from signed URL
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(document_url, timeout=120.0)
                    response.raise_for_status()
                    pdf_bytes = response.content

                activity.logger.info(
                    f"Loaded PDF bytes for coordinate extraction: {len(pdf_bytes)} bytes",
                    extra={"document_id": document_id}
                )
            except Exception as e:
                activity.logger.warning(
                    f"Could not load PDF bytes for coordinate extraction: {e}",
                    extra={"document_id": document_id, "error": str(e)}
                )

            # Create pipeline and extract pages
            pipeline = OCRExtractionPipeline(session)

            # Pass (signed) document_url for coordinate extraction and page dimensions
            pages = await pipeline.extract_and_store_pages(
                document_id=UUID(document_id),
                document_url=document_url,
                pdf_bytes=pdf_bytes,
            )
            
            await session.commit()
            
            pages_processed = [int(p.page_number) for p in pages]
            markdown_pages = [(p.markdown, int(p.page_number), p.metadata) for p in pages]
            
            activity.logger.info(
                "OCR Extraction Complete",
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
