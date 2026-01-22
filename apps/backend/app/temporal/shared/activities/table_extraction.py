"""Temporal activity for table extraction."""

from temporalio import activity
from typing import Dict, Any, Optional, List
from uuid import UUID

from app.pipeline.table_extraction import TableExtractionPipeline
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry

LOGGER = get_logger(__name__)


@ActivityRegistry.register("shared", "extract_tables")
@activity.defn
async def extract_tables(
    workflow_id: str,
    document_id: str,
    document_url: Optional[str] = None,
    page_numbers: Optional[List[int]] = None
) -> Dict[str, Any]:
    """Extract and process tables from document."""
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
            
            pages_with_tables = []
            for page in pages:
                has_tables = False
                if page.metadata:
                    has_tables = page.metadata.get("has_tables", False)
                
                if page_numbers and page.page_number not in page_numbers:
                    continue
                
                if has_tables:
                    pages_with_tables.append(page)
            
            if not pages_with_tables:
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
            
            page_data_list = []
            for page in pages_with_tables:
                page_data = PageData(
                    page_number=page.page_number,
                    text=page.text or "",
                    markdown=page.markdown or page.text or "",
                    metadata=page.metadata or {}
                )
                if not page_data.metadata.get("document_id"):
                    page_data.metadata["document_id"] = str(document_id)
                page_data.metadata["source"] = "database"
                page_data_list.append(page_data)
            
            pipeline = TableExtractionPipeline(session)
            result = await pipeline.extract_and_process_tables(
                document_id=UUID(document_id),
                document_url=document_url or "",
                docling_result=None,
                pages=page_data_list,
                page_numbers=page_numbers
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(f"Table extraction failed for document {document_id}: {e}", exc_info=True)
            raise
