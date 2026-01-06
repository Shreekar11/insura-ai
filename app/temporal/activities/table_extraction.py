"""Temporal activity for table extraction.

This activity extracts and processes tables from documents using
the TableExtractionPipeline.
"""

from temporalio import activity
from typing import Dict, Any, Optional, List
from uuid import UUID

from app.pipeline.table_extraction import TableExtractionPipeline
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@activity.defn
async def extract_tables(
    workflow_id: str,
    document_id: str,
    document_url: Optional[str] = None,
    page_numbers: Optional[List[int]] = None
) -> Dict[str, Any]:
    """Extract and process tables from document.
    
    This activity extracts structured tables from documents, classifies them,
    normalizes rows, validates data, and persists to database.
    
    Tables are extracted from pages stored in the database (which have markdown
    content from Docling OCR extraction).
    
    Args:
        document_id: Document UUID as string
        document_url: Optional document URL (not used, kept for compatibility)
        page_numbers: Optional list of page numbers to process
        
    Returns:
        Dictionary with extraction results:
        - tables_found: Number of tables detected
        - tables_processed: Number of tables successfully processed
        - sov_items: Number of SOV items saved
        - loss_run_claims: Number of Loss Run claims saved
        - validation_passed: Whether all validations passed
        - validation_errors: Number of validation errors
        - validation_results: List of validation results per table
        - errors: List of processing errors
    """
    from app.core.database import async_session_maker
    from app.repositories.document_repository import DocumentRepository
    from app.models.page_data import PageData
    
    LOGGER.info(
        f"[Phase 5: Table Extraction] Starting table extraction for document: {document_id}",
        extra={
            "workflow_id": workflow_id,
            "document_id": document_id,
            "page_numbers": page_numbers
        }
    )
    
    async with async_session_maker() as session:
        try:
            # Get pages from database
            doc_repo = DocumentRepository(session)
            pages = await doc_repo.get_pages_by_document(document_id=UUID(document_id))
            
            if not pages:
                LOGGER.warning(
                    f"No pages found for document {document_id}",
                    extra={"document_id": document_id}
                )
                return {
                    "tables_found": 0,
                    "tables_processed": 0,
                    "sov_items": 0,
                    "loss_run_claims": 0,
                    "validation_passed": True,
                    "validation_errors": 0,
                    "validation_results": [],
                    "errors": []
                }
            
            # Filter pages: only process pages that have tables (has_tables=True from OCR)
            # Also filter by page_numbers if specified
            pages_with_tables = []
            for page in pages:
                # Check if page has tables metadata
                has_tables = False
                if page.metadata:
                    has_tables = page.metadata.get("has_tables", False)
                
                # Filter by page_numbers if specified
                if page_numbers and page.page_number not in page_numbers:
                    continue
                
                # Only include pages with tables
                if has_tables:
                    pages_with_tables.append(page)
            
            LOGGER.info(
                f"Found {len(pages_with_tables)} pages with tables (out of {len(pages)} total pages)",
                extra={
                    "document_id": document_id,
                    "total_pages": len(pages),
                    "pages_with_tables": len(pages_with_tables),
                    "page_numbers": [p.page_number for p in pages_with_tables]
                }
            )
            
            if not pages_with_tables:
                LOGGER.info(
                    f"No pages with tables found for document {document_id}",
                    extra={"document_id": document_id}
                )
                return {
                    "tables_found": 0,
                    "tables_processed": 0,
                    "sov_items": 0,
                    "loss_run_claims": 0,
                    "validation_passed": True,
                    "validation_errors": 0,
                    "validation_results": [],
                    "errors": []
                }
            
            # Convert database pages to PageData objects, preserving metadata
            page_data_list = []
            for page in pages_with_tables:
                page_data = PageData(
                    page_number=page.page_number,
                    text=page.text or "",
                    markdown=page.markdown or page.text or "",
                    metadata=page.metadata or {}  # Preserve existing metadata including has_tables
                )
                # Ensure document_id is in metadata
                if not page_data.metadata.get("document_id"):
                    page_data.metadata["document_id"] = str(document_id)
                page_data.metadata["source"] = "database"
                page_data_list.append(page_data)
            
            # Initialize pipeline
            pipeline = TableExtractionPipeline(session)
            
            # Extract and process tables from pages
            result = await pipeline.extract_and_process_tables(
                document_id=UUID(document_id),
                document_url=document_url or "",
                docling_result=None,  # Extract from pages instead
                pages=page_data_list,
                page_numbers=page_numbers
            )
            
            LOGGER.info(
                f"[Phase 5: Table Extraction] Complete: {result['tables_processed']} tables processed, "
                f"{result['sov_items']} SOV items, {result['loss_run_claims']} Loss Run claims",
                extra={
                    "document_id": document_id,
                    **result
                }
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(
                f"[Phase 5: Table Extraction] Failed for document {document_id}: {e}",
                exc_info=True,
                extra={"document_id": document_id}
            )
            raise

