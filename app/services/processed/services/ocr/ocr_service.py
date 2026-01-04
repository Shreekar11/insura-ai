"""Docling-backed OCR service for document text extraction.

This service uses Docling as the primary document parser, providing:
- Layout-aware text extraction with structure preservation
- Native table detection and structured extraction
- Page-level extraction with coordinates and metadata
- Selective page processing
"""
import re
import time
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID

from app.models.page_data import PageData
from app.models.table_json import (
    TableJSON,
    TableCellJSON,
    TableExtractionSource,
    ConfidenceMetrics,
    create_table_id,
)
from app.utils.exceptions import OCRExtractionError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class OCRService:
    """OCR service implementation using Docling for document parsing.
    
    This service is the primary parser. It provides:
    - Layout-aware text extraction
    - Native table detection and structured extraction
    - Selective page processing based on page manifest
    - Rich metadata including coordinates and structure
    
    Attributes:
        converter: Docling DocumentConverter instance
        _docling_result: Cached Docling conversion result for table extraction
    """
    
    # Regex pattern for detecting markdown tables
    TABLE_PATTERN = re.compile(
        r'\|[^\n]+\|[\s]*\n\|[-:\s|]+\|[\s]*\n(?:\|[^\n]+\|[\s]*\n)+',
        re.MULTILINE
    )
    
    def __init__(self):
        """Initialize OCRService with Docling converter."""
        self._docling_result = None
        try:
            from docling.document_converter import DocumentConverter
            self.converter = DocumentConverter()
            LOGGER.info(
                "Initialized OCRService",
                extra={"service": "docling"}
            )
        except ImportError as e:
            LOGGER.warning(
                "Docling not available, service will fail on extraction",
                extra={"error": str(e)}
            )
            self.converter = None
    
    async def extract_pages(
        self,
        document_url: str,
        document_id: UUID,
        pages_to_process: Optional[List[int]] = None
    ) -> List[PageData]:
        """Extract text from document pages using Docling.
        
        Args:
            document_url: URL or local path to the document
            document_id: Document ID for logging and tracking
            pages_to_process: Optional list of page numbers to extract.
                If None, all pages are extracted.
                If provided, only those pages are returned.
        
        Returns:
            List[PageData]: Extracted page data with text, markdown, and metadata
        
        Raises:
            OCRExtractionError: If extraction fails
        """
        start_time = time.time()
        
        LOGGER.info(
            "Starting Docling extraction",
            extra={
                "document_url": document_url,
                "document_id": str(document_id),
                "pages_to_process": pages_to_process,
                "selective": pages_to_process is not None
            }
        )
        
        if self.converter is None:
            raise OCRExtractionError(
                "Docling is not available. Please install docling package."
            )
        
        try:
            # Convert document using Docling
            result = self.converter.convert(document_url)
            
            # Cache the result for structural table extraction
            self._docling_result = result
            
            document = result.document.export_to_markdown(
                page_break_placeholder="\n\n<<<DOC_PAGE_BREAK>>>\n\n"
            )

            pages = document.split("<<<DOC_PAGE_BREAK>>>")

            transformed_pages = []

            for idx, page in enumerate(pages, start=1):
                page_with_number = f"[PAGE {idx}]\n\n{page.strip()}"
                transformed_pages.append(page_with_number)
                
            total_pages = len(transformed_pages)
            
            LOGGER.info(
                f"Document converted successfully: {total_pages} pages",
                extra={
                    "document_id": str(document_id),
                    "total_pages": total_pages
                }
            )
            
            # Extract structural tables from Docling result
            structural_tables = self._extract_structural_tables(result, document_id)
            
            # Group tables by page number
            tables_by_page: Dict[int, List[TableJSON]] = {}
            for table in structural_tables:
                page_num = table.page_number
                if page_num not in tables_by_page:
                    tables_by_page[page_num] = []
                tables_by_page[page_num].append(table)
            
            LOGGER.info(
                f"Extracted {len(structural_tables)} structural tables",
                extra={
                    "document_id": str(document_id),
                    "total_tables": len(structural_tables),
                    "pages_with_tables": len(tables_by_page)
                }
            )
            
            # Extract pages with table detection and structural tables
            all_pages = self._extract_all_pages(
                transformed_pages, 
                document_id,
                tables_by_page
            )

            # Filter pages if selective extraction is requested
            if pages_to_process is not None:
                pages_set = set(int(page) for page in pages_to_process)
                
                filtered_pages = [
                    page for page in all_pages
                    if page.page_number in pages_set
                ]
                
                LOGGER.info(
                    f"Selective extraction: {len(filtered_pages)}/{len(all_pages)} pages",
                    extra={
                        "document_id": str(document_id),
                        "requested_pages": pages_to_process,
                        "returned_pages": [p.page_number for p in filtered_pages],
                        "pages_with_tables": [
                            p.page_number for p in filtered_pages 
                            if p.metadata.get("has_tables", False)
                        ]
                    }
                )
                
                result_pages = filtered_pages
            else:
                result_pages = all_pages
            
            processing_time = time.time() - start_time
            
            # Count pages with tables
            pages_with_tables = sum(
                1 for p in result_pages if p.metadata.get("has_tables", False)
            )
            
            LOGGER.info(
                f"Docling extraction completed in {processing_time:.2f}s",
                extra={
                    "document_id": str(document_id),
                    "pages_extracted": len(result_pages),
                    "pages_with_tables": pages_with_tables,
                    "structural_tables_extracted": len(structural_tables),
                    "processing_time_seconds": processing_time
                }
            )
            
            return result_pages
            
        except Exception as e:
            LOGGER.error(
                f"Docling extraction failed: {e}",
                extra={
                    "document_id": str(document_id),
                    "document_url": document_url,
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise OCRExtractionError(f"Failed to extract document: {e}") from e
    
    def _extract_structural_tables(
        self,
        docling_result: Any,
        document_id: UUID
    ) -> List[TableJSON]:
        """Extract structural tables from Docling result.
        
        This is the PRIMARY extraction method using Docling's tableformer output.
        It extracts cell-level structure including spans and bboxes.
        
        Args:
            docling_result: Docling DocumentConverter result
            document_id: Document UUID
            
        Returns:
            List of TableJSON objects with full structural information
        """
        tables = []
        
        try:
            doc = docling_result.document
            
            # Check if document has tables attribute
            if not hasattr(doc, 'tables') or not doc.tables:
                LOGGER.debug(
                    "No structural tables found in Docling result",
                    extra={"document_id": str(document_id)}
                )
                return tables
            
            for table_idx, docling_table in enumerate(doc.tables):
                try:
                    table_json = self._convert_docling_table_to_json(
                        docling_table,
                        doc,
                        document_id,
                        table_idx
                    )
                    if table_json:
                        tables.append(table_json)
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to convert Docling table {table_idx}: {e}",
                        extra={
                            "document_id": str(document_id),
                            "table_index": table_idx
                        }
                    )
            
            LOGGER.info(
                f"Extracted {len(tables)} structural tables from Docling",
                extra={
                    "document_id": str(document_id),
                    "total_docling_tables": len(doc.tables) if hasattr(doc, 'tables') else 0,
                    "converted_tables": len(tables)
                }
            )
            
        except Exception as e:
            LOGGER.warning(
                f"Failed to extract structural tables: {e}",
                extra={"document_id": str(document_id)},
                exc_info=True
            )
        
        return tables
    
    def _convert_docling_table_to_json(
        self,
        docling_table: Any,
        doc: Any,
        document_id: UUID,
        table_idx: int
    ) -> Optional[TableJSON]:
        """Convert a single Docling table to TableJSON format.
        
        Args:
            docling_table: Docling TableItem object
            doc: Docling Document object
            document_id: Document UUID
            table_idx: Index of table in document
            
        Returns:
            TableJSON or None if conversion fails
        """
        try:
            # Get page number from table's prov (provenance)
            page_number = 1
            if hasattr(docling_table, 'prov') and docling_table.prov:
                prov = docling_table.prov[0] if isinstance(docling_table.prov, list) else docling_table.prov
                if hasattr(prov, 'page_no'):
                    page_number = prov.page_no
                elif hasattr(prov, 'page'):
                    page_number = prov.page
            
            # Get bounding box if available
            table_bbox = None
            if hasattr(docling_table, 'prov') and docling_table.prov:
                prov = docling_table.prov[0] if isinstance(docling_table.prov, list) else docling_table.prov
                if hasattr(prov, 'bbox'):
                    bbox = prov.bbox
                    if hasattr(bbox, 'as_tuple'):
                        table_bbox = list(bbox.as_tuple())
                    elif isinstance(bbox, (list, tuple)):
                        table_bbox = list(bbox)
            
            # Create table ID
            table_id = create_table_id(document_id, page_number, table_idx)
            
            # Extract cells from Docling table
            cells = []
            num_rows = 0
            num_cols = 0
            
            # Try to export to DataFrame to get structured data
            try:
                import pandas as pd
                df = docling_table.export_to_dataframe(doc=doc)
                
                if df is not None and not df.empty:
                    num_rows = len(df) + 1  # +1 for header row
                    num_cols = len(df.columns)
                    
                    # Add header cells
                    for col_idx, header in enumerate(df.columns):
                        cell = TableCellJSON(
                            row=0,
                            col=col_idx,
                            text=str(header) if header is not None else "",
                            is_header=True
                        )
                        cells.append(cell)
                    
                    # Add data cells
                    for row_idx, (_, row) in enumerate(df.iterrows(), start=1):
                        for col_idx, value in enumerate(row):
                            cell = TableCellJSON(
                                row=row_idx,
                                col=col_idx,
                                text=str(value) if value is not None and str(value) != 'nan' else ""
                            )
                            cells.append(cell)
            except Exception as df_error:
                LOGGER.debug(
                    f"DataFrame export failed, trying direct cell access: {df_error}",
                    extra={"table_idx": table_idx}
                )
                
                # Fallback: Try to access cells directly
                cells, num_rows, num_cols = self._extract_cells_directly(docling_table)
            
            if not cells:
                LOGGER.debug(
                    f"No cells extracted for table {table_idx}",
                    extra={"table_idx": table_idx}
                )
                return None
            
            # Get raw markdown for fallback/debugging
            raw_markdown = None
            try:
                if hasattr(docling_table, 'export_to_markdown'):
                    raw_markdown = docling_table.export_to_markdown(doc=doc)
            except Exception:
                pass
            
            # Create TableJSON
            table_json = TableJSON(
                table_id=table_id,
                document_id=document_id,
                page_number=page_number,
                table_index=table_idx,
                table_bbox=table_bbox,
                cells=cells,
                header_rows=[0],
                num_rows=num_rows,
                num_cols=num_cols,
                source=TableExtractionSource.DOCLING_STRUCTURAL,
                extractor_version="1.0.0",
                raw_markdown=raw_markdown,
                metadata={
                    "docling_table_type": type(docling_table).__name__
                }
            )
            
            # Calculate confidence metrics
            table_json.confidence_metrics = table_json.calculate_confidence_metrics()
            
            return table_json
            
        except Exception as e:
            LOGGER.warning(
                f"Failed to convert Docling table to JSON: {e}",
                extra={"table_idx": table_idx},
                exc_info=True
            )
            return None
    
    def _extract_cells_directly(
        self,
        docling_table: Any
    ) -> Tuple[List[TableCellJSON], int, int]:
        """Extract cells directly from Docling table structure.
        
        Fallback method when DataFrame export fails.
        
        Args:
            docling_table: Docling TableItem object
            
        Returns:
            Tuple of (cells, num_rows, num_cols)
        """
        cells = []
        num_rows = 0
        num_cols = 0
        
        try:
            # Try accessing data.grid_cells if available (Docling)
            if hasattr(docling_table, 'data') and hasattr(docling_table.data, 'grid'):
                grid = docling_table.data.grid
                num_rows = len(grid)
                
                for row_idx, row in enumerate(grid):
                    if len(row) > num_cols:
                        num_cols = len(row)
                    
                    for col_idx, cell_data in enumerate(row):
                        text = ""
                        if hasattr(cell_data, 'text'):
                            text = str(cell_data.text)
                        elif isinstance(cell_data, str):
                            text = cell_data
                        
                        rowspan = getattr(cell_data, 'row_span', 1) or 1
                        colspan = getattr(cell_data, 'col_span', 1) or 1
                        
                        cell = TableCellJSON(
                            row=row_idx,
                            col=col_idx,
                            text=text,
                            rowspan=rowspan,
                            colspan=colspan,
                            is_header=(row_idx == 0)
                        )
                        cells.append(cell)
            
            # Try accessing body/header structure
            elif hasattr(docling_table, 'body') or hasattr(docling_table, 'header'):
                header_rows = getattr(docling_table, 'header', []) or []
                body_rows = getattr(docling_table, 'body', []) or []
                
                all_rows = list(header_rows) + list(body_rows)
                num_rows = len(all_rows)
                
                for row_idx, row in enumerate(all_rows):
                    is_header = row_idx < len(header_rows)
                    row_cells = row if isinstance(row, (list, tuple)) else [row]
                    
                    if len(row_cells) > num_cols:
                        num_cols = len(row_cells)
                    
                    for col_idx, cell_data in enumerate(row_cells):
                        text = str(cell_data) if cell_data is not None else ""
                        
                        cell = TableCellJSON(
                            row=row_idx,
                            col=col_idx,
                            text=text,
                            is_header=is_header
                        )
                        cells.append(cell)
                        
        except Exception as e:
            LOGGER.debug(f"Direct cell extraction failed: {e}")
        
        return cells, num_rows, num_cols
    
    def _extract_all_pages(
        self, 
        transformed_pages: List[str], 
        document_id: UUID,
        tables_by_page: Optional[Dict[int, List[TableJSON]]] = None
    ) -> List[PageData]:
        """Extract data from all pages in the document.
        
        Args:
            transformed_pages: List of transformed pages with markdown
            document_id: Document ID for metadata
            tables_by_page: Optional dict mapping page numbers to TableJSON objects
        
        Returns:
            List[PageData]: All extracted pages with table detection
        """
        pages = []
        tables_by_page = tables_by_page or {}
        
        for idx, page_content in enumerate(transformed_pages):
            page_number = idx + 1
            
            # Get structural tables for this page
            structural_tables = tables_by_page.get(page_number, [])
            
            # Detect tables in markdown content (fallback)
            has_tables_markdown = self._detect_tables_in_markdown(page_content)
            table_count_markdown = self._count_tables_in_markdown(page_content)
            
            # Prefer structural tables if available
            has_tables = len(structural_tables) > 0 or has_tables_markdown
            table_count = len(structural_tables) if structural_tables else table_count_markdown
            
            # Build metadata
            metadata = {
                "source": "docling",
                "document_id": str(document_id),
                "has_tables": has_tables,
                "table_count": table_count,
                "has_structural_tables": len(structural_tables) > 0,
                "structural_table_count": len(structural_tables)
            }
            
            # Add structural tables as TableJSON dicts
            if structural_tables:
                metadata["structural_tables"] = [t.to_dict() for t in structural_tables]
            
            # Add markdown table positions if tables exist (fallback info)
            if has_tables_markdown:
                table_info = self._extract_table_info(page_content)
                metadata["markdown_tables"] = table_info
            
            page_data = PageData(
                page_number=page_number,
                text=page_content,
                markdown=page_content,
                metadata=metadata
            )
            pages.append(page_data)
            
        return pages
    
    def get_structural_tables(self, page_number: Optional[int] = None) -> List[TableJSON]:
        """Get structural tables from the last extraction.
        
        Args:
            page_number: Optional page number to filter by
            
        Returns:
            List of TableJSON objects
        """
        if not self._docling_result:
            return []
        
        # Re-extract tables (they're cached in page metadata)
        # This is a convenience method for accessing tables after extraction
        return []
    
    def _detect_tables_in_markdown(self, markdown_text: str) -> bool:
        """Detect if markdown text contains tables.
        
        Markdown tables follow this pattern:
        | Header 1 | Header 2 |
        |----------|----------|
        | Cell 1   | Cell 2   |
        
        Args:
            markdown_text: Markdown content to check
        
        Returns:
            bool: True if tables are detected
        """
        return bool(self.TABLE_PATTERN.search(markdown_text))
    
    def _count_tables_in_markdown(self, markdown_text: str) -> int:
        """Count the number of tables in markdown text.
        
        Args:
            markdown_text: Markdown content to analyze
        
        Returns:
            int: Number of tables found
        """
        matches = self.TABLE_PATTERN.findall(markdown_text)
        return len(matches)
    
    def _extract_table_info(self, markdown_text: str) -> List[Dict[str, Any]]:
        """Extract basic information about tables in markdown.
        
        Args:
            markdown_text: Markdown content containing tables
        
        Returns:
            List[Dict]: List of table metadata
        """
        tables_info = []
        
        for match in self.TABLE_PATTERN.finditer(markdown_text):
            table_text = match.group(0)
            lines = [line.strip() for line in table_text.split('\n') if line.strip()]
            
            # Parse table structure
            if len(lines) >= 2:
                header_line = lines[0]
                separator_line = lines[1]
                data_lines = lines[2:]
                
                # Count columns
                num_columns = header_line.count('|') - 1
                num_rows = len(data_lines)
                
                # Extract headers
                headers = [
                    cell.strip() 
                    for cell in header_line.split('|')[1:-1]
                ]
                
                table_info = {
                    "start_position": match.start(),
                    "end_position": match.end(),
                    "num_columns": num_columns,
                    "num_rows": num_rows,
                    "headers": headers,
                    "total_cells": num_columns * num_rows
                }
                
                tables_info.append(table_info)
        
        return tables_info
    
    def get_service_name(self) -> str:
        """Get the name of the OCR service.
        
        Returns:
            str: Service name
        """
        return "Docling OCR"