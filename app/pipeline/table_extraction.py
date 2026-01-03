"""Table extraction pipeline for Phase 5.

This pipeline orchestrates the complete table extraction process:
1. Extract structured tables from Docling as TableJSON
2. Persist tables as first-class entities (DocumentTable)
3. Classify table types
4. Canonicalize headers
5. Normalize rows into domain objects
6. Validate extracted data
7. Persist domain objects (SOV items, Loss Run claims)

The PRIMARY extraction uses Docling's tableformer output with cell-level structure.
Tables are stored as TableJSON in the document_tables table for debugging and reprocessing.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.table_json import TableJSON, TableType
from app.services.extracted.services.extraction.table import (
    TableExtractionService,
    TableStructure,
    TableClassificationService,
    TableClassification,
    HeaderCanonicalizationService,
    ColumnMapping,
    RowNormalizationService,
    TableValidationService,
    ValidationResult,
)
from app.repositories.table_repository import TableRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class TableExtractionPipeline:
    """Pipeline for extracting and processing tables from documents.
    
    This pipeline implements Phase 5 table extraction following the v2 architecture:
    - Tables are extracted structurally as TableJSON (not as text)
    - Tables are persisted as first-class entities (DocumentTable)
    - LLM is only used when needed (column meaning ambiguous, validation fails)
    - Domain objects (SOV, Loss Run) are validated and persisted
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize table extraction pipeline.
        
        Args:
            session: Database session
        """
        self.session = session
        self.table_extractor = TableExtractionService()
        self.table_classifier = TableClassificationService()
        self.header_canonicalizer = HeaderCanonicalizationService()
        self.row_normalizer = RowNormalizationService()
        self.validator = TableValidationService()
        self.table_repo = TableRepository(session)
        
        LOGGER.info("Initialized TableExtractionPipeline")
    
    async def extract_and_process_tables(
        self,
        document_id: UUID,
        document_url: str,
        docling_result: Optional[Any] = None,
        pages: Optional[List[Any]] = None,
        page_numbers: Optional[List[int]] = None,
        persist_tables: bool = True
    ) -> Dict[str, Any]:
        """Extract and process tables from document.
        
        Args:
            document_id: Document ID
            document_url: Document URL or path
            docling_result: Optional Docling conversion result
            pages: Optional list of PageData objects
            page_numbers: Optional list of page numbers to process
            persist_tables: Whether to persist tables as DocumentTable (default True)
            
        Returns:
            Dictionary with extraction results and statistics
        """
        LOGGER.info(
            f"Starting table extraction for document {document_id}",
            extra={
                "document_id": str(document_id),
                "has_docling_result": docling_result is not None,
                "pages_provided": pages is not None,
                "page_numbers": page_numbers,
                "persist_tables": persist_tables
            }
        )
        
        # Step 1: Extract structured tables as TableJSON
        # PRIMARY: Uses Docling structural tables from page metadata
        # FALLBACK: Parses markdown tables if structural not available
        all_table_json: List[TableJSON] = []
        all_tables: List[TableStructure] = []
        page_context_map: Dict[int, str] = {}
        
        if pages:
            # Extract tables as TableJSON (full structural data)
            all_table_json = self.table_extractor.extract_tables_as_json(
                pages, 
                document_id
            )
            
            # Also get as TableStructure for compatibility with existing services
            page_tables = self.table_extractor.extract_tables_from_pages(pages)
            for page_num, tables in page_tables.items():
                if page_numbers is None or page_num in page_numbers:
                    all_tables.extend(tables)
            
            # Build page context map for classification
            for page in pages:
                page_num = getattr(page, 'page_number', None) or getattr(page, 'page', None)
                if page_num:
                    page_text = getattr(page, 'markdown', None) or getattr(page, 'text', '') or ''
                    page_context_map[page_num] = page_text
            
            LOGGER.info(
                f"Extracted {len(all_table_json)} tables as TableJSON from {len(pages)} pages",
                extra={
                    "document_id": str(document_id),
                    "pages_processed": len(pages),
                    "tables_found": len(all_table_json),
                    "structural_tables": sum(
                        1 for t in all_table_json 
                        if t.source.value == "docling_structural"
                    ),
                    "markdown_tables": sum(
                        1 for t in all_table_json 
                        if t.source.value == "docling_markdown"
                    )
                }
            )
        elif docling_result:
            LOGGER.warning("Using Docling result fallback - prefer pages from database")
            all_tables = self.table_extractor.extract_tables_from_docling_result(
                docling_result
            )
        else:
            LOGGER.warning("No pages or docling_result provided for table extraction")
            return {
                "tables_found": 0,
                "tables_persisted": 0,
                "tables_processed": 0,
                "sov_items": 0,
                "loss_run_claims": 0,
                "validation_passed": True,
                "validation_errors": 0,
                "validation_results": [],
                "errors": []
            }
        
        # Step 2: Persist tables as DocumentTable (first-class storage)
        tables_persisted = 0
        if persist_tables and all_table_json:
            try:
                tables_persisted = await self.table_repo.save_tables_json(
                    document_id, 
                    all_table_json
                )
                LOGGER.info(
                    f"Persisted {tables_persisted} tables as DocumentTable",
                    extra={
                        "document_id": str(document_id),
                        "tables_persisted": tables_persisted
                    }
                )
            except Exception as e:
                LOGGER.error(
                    f"Failed to persist tables: {e}",
                    extra={"document_id": str(document_id)},
                    exc_info=True
                )
        
        # Process each table for domain extraction
        sov_items = []
        loss_run_claims = []
        validation_results = []
        errors = []
        
        for table in all_tables:
            try:
                # Get page context for classification
                page_context = page_context_map.get(table.page_number, "")
                
                # Step 3: Classify table type using page context
                classification = self.table_classifier.classify_table(table, page_context)
                
                LOGGER.info(
                    f"Classified table {table.table_id} as {classification.table_type}",
                    extra={
                        "table_id": table.table_id,
                        "table_type": classification.table_type,
                        "confidence": classification.confidence,
                        "page_number": table.page_number,
                        "headers": table.headers[:5] if table.headers else [],
                        "reasoning": classification.reasoning,
                        "source": table.source
                    }
                )
                
                # Update classification in persisted table
                if persist_tables and table.table_json:
                    try:
                        await self.table_repo.update_table_classification(
                            table.table_json.table_id,
                            classification.table_type,
                            classification.confidence,
                            classification.reasoning
                        )
                    except Exception as e:
                        LOGGER.warning(
                            f"Failed to update table classification: {e}",
                            extra={"table_id": table.table_id}
                        )
                
                # Skip non-SOV/Loss Run tables for now
                if classification.table_type not in ["property_sov", "loss_run"]:
                    LOGGER.debug(
                        f"Skipping table {table.table_id} (type: {classification.table_type})",
                        extra={"table_id": table.table_id, "table_type": classification.table_type}
                    )
                    continue
                
                # Step 4: Canonicalize headers
                column_mappings = self.header_canonicalizer.canonicalize_headers(
                    table,
                    classification.table_type
                )
                
                # Step 5: Normalize rows into domain objects
                if classification.table_type == "property_sov":
                    items = self.row_normalizer.normalize_rows(
                        table,
                        column_mappings,
                        classification,
                        str(document_id)
                    )
                    sov_items.extend(items)
                    
                    # Step 6: Validate SOV table
                    validation = self.validator.validate_sov_table(items)
                    validation_results.append({
                        "table_id": table.table_id,
                        "table_type": "property_sov",
                        "validation": validation
                    })
                    
                elif classification.table_type == "loss_run":
                    claims = self.row_normalizer.normalize_rows(
                        table,
                        column_mappings,
                        classification,
                        str(document_id)
                    )
                    loss_run_claims.extend(claims)
                    
                    # Step 6: Validate Loss Run table
                    validation = self.validator.validate_loss_run_table(claims)
                    validation_results.append({
                        "table_id": table.table_id,
                        "table_type": "loss_run",
                        "validation": validation
                    })
                
            except Exception as e:
                LOGGER.error(
                    f"Error processing table {table.table_id}: {e}",
                    exc_info=True,
                    extra={"table_id": table.table_id}
                )
                errors.append({
                    "table_id": table.table_id,
                    "error": str(e)
                })
        
        # Step 7: Persist domain objects to database
        sov_count = 0
        loss_run_count = 0
        
        if sov_items:
            sov_count = await self.table_repo.save_sov_items(document_id, sov_items)
            LOGGER.info(
                f"Saved {sov_count} SOV items",
                extra={"document_id": str(document_id), "items_count": len(sov_items)}
            )
        
        if loss_run_claims:
            loss_run_count = await self.table_repo.save_loss_run_claims(document_id, loss_run_claims)
            LOGGER.info(
                f"Saved {loss_run_count} loss run claims",
                extra={"document_id": str(document_id), "claims_count": len(loss_run_claims)}
            )
        
        # Aggregate validation results
        all_passed = all(
            result["validation"].passed
            for result in validation_results
        ) if validation_results else True
        
        total_errors = sum(
            len(result["validation"].issues)
            for result in validation_results
            if not result["validation"].passed
        )
        
        result = {
            "tables_found": len(all_tables),
            "tables_persisted": tables_persisted,
            "tables_processed": len(validation_results),
            "sov_items": sov_count,
            "loss_run_claims": loss_run_count,
            "validation_passed": all_passed,
            "validation_errors": total_errors,
            "validation_results": [
                {
                    "table_id": r["table_id"],
                    "table_type": r["table_type"],
                    "passed": r["validation"].passed,
                    "issue_count": len(r["validation"].issues),
                    "summary": r["validation"].summary
                }
                for r in validation_results
            ],
            "errors": errors
        }
        
        LOGGER.info(
            f"Table extraction complete for document {document_id}",
            extra={
                "document_id": str(document_id),
                **result
            }
        )
        
        return result
    
    async def get_document_tables(
        self,
        document_id: UUID,
        page_number: Optional[int] = None,
        table_type: Optional[str] = None
    ) -> List[TableJSON]:
        """Get tables for a document as TableJSON objects.
        
        Args:
            document_id: Document ID
            page_number: Optional page number filter
            table_type: Optional table type filter
            
        Returns:
            List of TableJSON objects
        """
        return await self.table_repo.get_tables_as_json(
            document_id,
            page_number,
            table_type
        )

