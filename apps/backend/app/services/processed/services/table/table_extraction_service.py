"""Table extraction service for structured table parsing.

This service implements Phase 5 table extraction:
- Step 1: Table Detection (Layout First, No Semantics)
- Step 2: Structural Table Parsing (Rows & Columns) via TableJSON
- Step 3: Header Canonicalization (Domain Mapping)
- Step 4: Row Normalization into Domain Objects
- Step 5: Validation & Reconciliation
- Step 6: Table Classification (SOV vs Loss Run vs Other)

Tables are extracted structurally from Docling output as TableJSON, not as text.
The PRIMARY extraction uses Docling's tableformer output with cell-level structure.
Markdown parsing is used as a FALLBACK when structural extraction fails.
"""

from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
import re

from app.models.table_json import (
    TableJSON,
    TableCellJSON,
    TableExtractionSource,
    ConfidenceMetrics,
    create_table_id,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class TableCell:
    """Represents a single table cell (legacy compatibility)."""
    
    row_index: int
    col_index: int
    value: str
    is_header: bool = False


@dataclass
class TableStructure:
    """Represents a structured table with rows and columns.
    
    This is a simplified view of TableJSON for compatibility with
    existing classification and normalization services.
    """
    
    table_id: str
    page_number: int
    bbox: Optional[List[float]] = None  # [x1, y1, x2, y2]
    confidence: float = 1.0
    headers: List[str] = None
    rows: List[List[str]] = None  # Raw cell values as strings
    num_rows: int = 0
    num_columns: int = 0
    source: str = "markdown"  # docling_structural, markdown
    table_json: Optional[TableJSON] = None  # Full TableJSON if available
    
    def __post_init__(self):
        """Initialize default values."""
        if self.headers is None:
            self.headers = []
        if self.rows is None:
            self.rows = []
        if self.num_rows == 0 and self.rows:
            self.num_rows = len(self.rows)
        if self.num_columns == 0 and self.headers:
            self.num_columns = len(self.headers)
    
    @classmethod
    def from_table_json(cls, table_json: TableJSON) -> "TableStructure":
        """Create TableStructure from TableJSON.
        
        Args:
            table_json: TableJSON object
            
        Returns:
            TableStructure with simplified view
        """
        return cls(
            table_id=table_json.table_id,
            page_number=table_json.page_number,
            bbox=table_json.table_bbox,
            confidence=table_json.confidence_metrics.overall,
            headers=table_json.canonical_headers,
            rows=table_json.get_data_rows(),
            num_rows=table_json.num_rows - len(table_json.header_rows),
            num_columns=table_json.num_cols,
            source=table_json.source.value if isinstance(table_json.source, TableExtractionSource) else str(table_json.source),
            table_json=table_json
        )


@dataclass
class ColumnMapping:
    """Maps raw column headers to canonical insurance domain fields."""
    
    index: int
    raw_header: str
    canonical_field: str
    confidence: float = 1.0


@dataclass
class TableClassification:
    """Table type classification result."""
    
    table_type: str  # property_sov, loss_run, inland_marine_schedule, auto_schedule, premium_schedule, other
    confidence: float
    reasoning: Optional[str] = None


class TableExtractionService:
    """Service for extracting structured tables from documents.
    
    This service extracts tables structurally from Docling output as TableJSON,
    preserving row/column relationships, cell spans, and bounding boxes.
    
    PRIMARY extraction: Docling structural tables (tableformer output)
    FALLBACK extraction: Markdown table parsing
    """
    
    # Regex pattern for detecting markdown tables
    TABLE_PATTERN = re.compile(
        r'\|[^\n]+\|[\s]*\n\|[-:\s|]+\|[\s]*\n(?:\|[^\n]+\|[\s]*\n)+',
        re.MULTILINE
    )
    
    def __init__(self):
        """Initialize table extraction service."""
        LOGGER.info("Initialized TableExtractionService")
    
    def extract_tables_from_pages(
        self,
        pages: List[Any],
        docling_result: Optional[Any] = None
    ) -> Dict[int, List[TableStructure]]:
        """Extract tables from multiple pages.
        
        This method extracts tables from pages that are already marked with
        has_tables=True metadata from OCR extraction. It prefers structural
        tables (TableJSON) from page metadata, falling back to markdown parsing.
        
        Args:
            pages: List of PageData objects (should already be filtered by has_tables=True)
            docling_result: Optional Docling result (not used, kept for compatibility)
            
        Returns:
            Dictionary mapping page numbers to list of TableStructure objects
        """
        page_tables: Dict[int, List[TableStructure]] = {}
        
        for page in pages:
            page_number = getattr(page, 'page_number', None) or getattr(page, 'page', None)
            if not page_number:
                continue
            
            page_tables[page_number] = []
            metadata = getattr(page, 'metadata', {}) or {}
            
            # PRIMARY: Try to use structural tables from page metadata
            structural_tables = metadata.get("structural_tables", [])
            if structural_tables:
                for table_dict in structural_tables:
                    try:
                        table_json = TableJSON.from_dict(table_dict)
                        
                        # Ensure headers are reconstructed if they're messy
                        if table_json._headers_need_reconstruction():
                            table_json.reconstruct_headers()
                        
                        table_structure = TableStructure.from_table_json(table_json)
                        page_tables[page_number].append(table_structure)
                    except Exception as e:
                        LOGGER.warning(
                            f"Failed to parse structural table from metadata: {e}",
                            extra={"page_number": page_number}
                        )
                
                LOGGER.debug(
                    f"Extracted {len(page_tables[page_number])} structural tables from page {page_number}",
                    extra={
                        "page_number": page_number,
                        "table_count": len(page_tables[page_number]),
                        "source": "docling_structural"
                    }
                )
                continue  # Skip markdown fallback if structural tables found
            
            # FALLBACK: Parse tables from markdown content
            markdown = getattr(page, 'markdown', None) or getattr(page, 'text', None)
            if markdown:
                tables = self._extract_tables_from_markdown(markdown, page_number)
                page_tables[page_number].extend(tables)
                
                if tables:
                    LOGGER.debug(
                        f"Extracted {len(tables)} tables from page {page_number} markdown (fallback)",
                        extra={
                            "page_number": page_number,
                            "table_count": len(tables),
                            "source": "markdown"
                        }
                    )
        
        # Remove empty entries
        page_tables = {k: v for k, v in page_tables.items() if v}
        
        return page_tables
    
    def extract_tables_as_json(
        self,
        pages: List[Any],
        document_id: Optional[UUID] = None
    ) -> List[TableJSON]:
        """Extract tables as TableJSON objects.
        
        This is the preferred method for getting full structural table data.
        
        Args:
            pages: List of PageData objects
            document_id: Optional document UUID
            
        Returns:
            List of TableJSON objects
        """
        all_tables: List[TableJSON] = []
        
        for page in pages:
            page_number = getattr(page, 'page_number', None) or getattr(page, 'page', None)
            if not page_number:
                continue
            
            metadata = getattr(page, 'metadata', {}) or {}
            
            # PRIMARY: Get structural tables from metadata
            structural_tables = metadata.get("structural_tables", [])
            for table_dict in structural_tables:
                try:
                    table_json = TableJSON.from_dict(table_dict)
                    
                    # Ensure headers are reconstructed if they're messy
                    if table_json._headers_need_reconstruction():
                        table_json.reconstruct_headers()
                    
                    if document_id and not table_json.document_id:
                        table_json.document_id = document_id
                    all_tables.append(table_json)
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to parse structural table: {e}",
                        extra={"page_number": page_number}
                    )
            
            # FALLBACK: Convert markdown tables to TableJSON
            if not structural_tables:
                markdown = getattr(page, 'markdown', None) or getattr(page, 'text', None)
                if markdown:
                    markdown_tables = self._extract_tables_from_markdown_as_json(
                        markdown, page_number, document_id
                    )
                    all_tables.extend(markdown_tables)
        
        LOGGER.info(
            f"Extracted {len(all_tables)} total tables as TableJSON",
            extra={
                "total_tables": len(all_tables),
                "structural_count": sum(
                    1 for t in all_tables 
                    if t.source == TableExtractionSource.DOCLING_STRUCTURAL
                ),
                "markdown_count": sum(
                    1 for t in all_tables 
                    if t.source == TableExtractionSource.DOCLING_MARKDOWN
                )
            }
        )
        
        return all_tables
    
    def _extract_tables_from_markdown_as_json(
        self,
        markdown: str,
        page_number: int,
        document_id: Optional[UUID] = None
    ) -> List[TableJSON]:
        """Extract tables from markdown as TableJSON objects.
        
        Args:
            markdown: Markdown content
            page_number: Page number
            document_id: Optional document UUID
            
        Returns:
            List of TableJSON objects
        """
        tables = []
        
        for match_idx, match in enumerate(self.TABLE_PATTERN.finditer(markdown)):
            table_text = match.group(0)
            lines = [line.strip() for line in table_text.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue
            
            # Parse header row
            header_line = lines[0]
            headers = [cell.strip() for cell in header_line.split('|')[1:-1]]
            
            # Create cells
            cells = []
            num_cols = len(headers)
            
            # Header cells
            for col_idx, header in enumerate(headers):
                cell = TableCellJSON(
                    row=0,
                    col=col_idx,
                    text=header,
                    is_header=True
                )
                cells.append(cell)
            
            # Data cells (skip separator line)
            for row_idx, line in enumerate(lines[2:], start=1):
                row_cells = [cell.strip() for cell in line.split('|')[1:-1]]
                
                for col_idx in range(num_cols):
                    cell_text = row_cells[col_idx] if col_idx < len(row_cells) else ""
                    cell = TableCellJSON(
                        row=row_idx,
                        col=col_idx,
                        text=cell_text
                    )
                    cells.append(cell)
            
            num_rows = len(lines) - 1  # Exclude separator
            table_id = create_table_id(document_id, page_number, match_idx)
            
            table_json = TableJSON(
                table_id=table_id,
                document_id=document_id,
                page_number=page_number,
                table_index=match_idx,
                cells=cells,
                header_rows=[0],
                num_rows=num_rows,
                num_cols=num_cols,
                canonical_headers=headers,
                source=TableExtractionSource.DOCLING_MARKDOWN,
                raw_markdown=table_text,
                confidence_metrics=ConfidenceMetrics(overall=0.85)  # Lower confidence for markdown
            )
            
            # Calculate actual confidence
            table_json.confidence_metrics = table_json.calculate_confidence_metrics()
            
            tables.append(table_json)
        
        return tables
    
    def _extract_tables_from_markdown(
        self,
        markdown: str,
        page_number: Optional[int]
    ) -> List[TableStructure]:
        """Extract tables from markdown as TableStructure (legacy format).
        
        This parses markdown tables into simplified TableStructure format
        for compatibility with existing classification/normalization services.
        
        Args:
            markdown: Markdown content
            page_number: Page number
            
        Returns:
            List of TableStructure objects
        """
        tables = []
        
        for match_idx, match in enumerate(self.TABLE_PATTERN.finditer(markdown)):
            table_text = match.group(0)
            lines = [line.strip() for line in table_text.split('\n') if line.strip()]
            
            if len(lines) < 2:
                continue
            
            # Parse header row
            header_line = lines[0]
            headers = [cell.strip() for cell in header_line.split('|')[1:-1]]
            
            # Parse data rows (skip separator line)
            rows = []
            for line in lines[2:]:
                row_cells = [cell.strip() for cell in line.split('|')[1:-1]]
                # Pad row if needed
                while len(row_cells) < len(headers):
                    row_cells.append("")
                rows.append(row_cells[:len(headers)])
            
            table_id = f"tbl_{page_number}_{match_idx}" if page_number else f"tbl_{match_idx}"
            
            table = TableStructure(
                table_id=table_id,
                page_number=page_number or 0,
                headers=headers,
                rows=rows,
                num_rows=len(rows),
                num_columns=len(headers),
                confidence=0.85,  # Markdown parsing is less reliable
                source="markdown"
            )
            
            tables.append(table)
        
        return tables
    
    def extract_tables_from_docling_result(
        self,
        docling_result: Any,
        page_number: Optional[int] = None
    ) -> List[TableStructure]:
        """Extract structured tables from Docling conversion result.
        
        NOTE: This is a FALLBACK method. Prefer using extract_tables_from_pages()
        which uses structural tables already extracted during OCR.
        
        Args:
            docling_result: Docling DocumentConverter result object
            page_number: Optional page number for filtering
            
        Returns:
            List of TableStructure objects with rows and columns
        """
        tables = []
        
        try:
            # Extract from markdown (simpler and more reliable than accessing Docling structure)
            markdown = docling_result.document.export_to_markdown()
            tables = self._extract_tables_from_markdown(markdown, page_number)
            
            LOGGER.info(
                f"Extracted {len(tables)} tables from Docling result markdown",
                extra={
                    "page_number": page_number,
                    "table_count": len(tables)
                }
            )
            
        except Exception as e:
            LOGGER.error(
                f"Failed to extract tables from Docling result: {e}",
                exc_info=True,
                extra={"page_number": page_number}
            )
        
        return tables
    
    def _extract_table_structure(
        self,
        docling_table: Any,
        page_number: Optional[int]
    ) -> Optional[TableStructure]:
        """Extract table structure from Docling table object.
        
        Args:
            docling_table: Docling table object
            page_number: Page number
            
        Returns:
            TableStructure or None if extraction fails
        """
        try:
            table_id = f"tbl_{page_number}_{id(docling_table)}" if page_number else f"tbl_{id(docling_table)}"
            
            # Extract headers
            headers = []
            rows = []
            
            # Try to access table structure
            if hasattr(docling_table, 'rows'):
                # Docling table has rows attribute
                for row_idx, row in enumerate(docling_table.rows):
                    row_cells = []
                    for cell in row:
                        cell_value = str(cell) if cell else ""
                        row_cells.append(cell_value)
                        
                        # First row is typically headers
                        if row_idx == 0:
                            headers.append(cell_value)
                    
                    if row_idx > 0:  # Skip header row for data rows
                        rows.append(row_cells)
            
            elif hasattr(docling_table, 'cells'):
                # Alternative: table has cells attribute
                # This would require reconstructing rows/columns from cell positions
                # For now, fall back to markdown parsing
                return None
            
            # Extract bounding box if available
            bbox = None
            if hasattr(docling_table, 'bbox'):
                bbox = list(docling_table.bbox)
            
            if not headers and not rows:
                return None
            
            return TableStructure(
                table_id=table_id,
                page_number=page_number or 0,
                bbox=bbox,
                headers=headers,
                rows=rows,
                num_rows=len(rows),
                num_columns=len(headers) if headers else (len(rows[0]) if rows else 0),
                source="docling_structural"
            )
            
        except Exception as e:
            LOGGER.warning(
                f"Failed to extract table structure: {e}",
                extra={"page_number": page_number}
            )
            return None

