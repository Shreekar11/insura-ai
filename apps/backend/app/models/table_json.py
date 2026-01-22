"""TableJSON schema for universal structured table representation.

This module defines the canonical schema for tables extracted from documents,
following the generalized table extraction architecture:
- Structure extraction (cells, rows, cols, spans, bboxes)
- Semantics (column/row meaning)
- Domain normalization (SOV/LossRun/etc.)

TableJSON is the first-class table representation stored in the database,
preserving full structural information for any table type.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum


class TableExtractionSource(str, Enum):
    """Source of table extraction."""
    
    DOCLING_STRUCTURAL = "docling_structural"
    DOCLING_MARKDOWN = "docling_markdown"
    CAMELOT = "camelot"
    TABULA = "tabula"
    PDFPLUMBER = "pdfplumber"
    MANUAL = "manual"


class TableType(str, Enum):
    """Classification of table types."""
    
    PROPERTY_SOV = "property_sov"
    LOSS_RUN = "loss_run"
    INLAND_MARINE_SCHEDULE = "inland_marine_schedule"
    AUTO_SCHEDULE = "auto_schedule"
    PREMIUM_SCHEDULE = "premium_schedule"
    COVERAGE_SUMMARY = "coverage_summary"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass
class TableCellJSON:
    """Represents a single table cell with structural information.
    
    Attributes:
        row: Row index (0-based)
        col: Column index (0-based)
        text: Cell text content
        rowspan: Number of rows this cell spans (default 1)
        colspan: Number of columns this cell spans (default 1)
        bbox: Bounding box coordinates [x1, y1, x2, y2] if available
        confidence: OCR/extraction confidence (0.0-1.0)
        is_header: Whether this cell is part of a header row
        is_row_header: Whether this cell is a row header (first column)
    """
    
    row: int
    col: int
    text: str
    rowspan: int = 1
    colspan: int = 1
    bbox: Optional[List[float]] = None
    confidence: float = 1.0
    is_header: bool = False
    is_row_header: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "row": self.row,
            "col": self.col,
            "text": self.text,
            "rowspan": self.rowspan,
            "colspan": self.colspan,
            "bbox": self.bbox,
            "confidence": self.confidence,
            "is_header": self.is_header,
            "is_row_header": self.is_row_header,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableCellJSON":
        """Create from dictionary."""
        return cls(
            row=data["row"],
            col=data["col"],
            text=data.get("text", ""),
            rowspan=data.get("rowspan", 1),
            colspan=data.get("colspan", 1),
            bbox=data.get("bbox"),
            confidence=data.get("confidence", 1.0),
            is_header=data.get("is_header", False),
            is_row_header=data.get("is_row_header", False),
        )


@dataclass
class ConfidenceMetrics:
    """Confidence metrics for table extraction quality.
    
    These metrics help select the best extraction when multiple
    extractors are used (ensemble approach).
    """
    
    overall: float = 1.0
    grid_completeness: float = 1.0
    column_consistency: float = 1.0
    span_sanity: float = 1.0
    numeric_coherence: float = 1.0
    header_likelihood: float = 1.0
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON serialization."""
        return {
            "overall": self.overall,
            "grid_completeness": self.grid_completeness,
            "column_consistency": self.column_consistency,
            "span_sanity": self.span_sanity,
            "numeric_coherence": self.numeric_coherence,
            "header_likelihood": self.header_likelihood,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfidenceMetrics":
        """Create from dictionary."""
        return cls(
            overall=data.get("overall", 1.0),
            grid_completeness=data.get("grid_completeness", 1.0),
            column_consistency=data.get("column_consistency", 1.0),
            span_sanity=data.get("span_sanity", 1.0),
            numeric_coherence=data.get("numeric_coherence", 1.0),
            header_likelihood=data.get("header_likelihood", 1.0),
        )


@dataclass
class TableJSON:
    """Universal structured table representation.
    
    This is the canonical schema for any detected table, preserving
    full structural information regardless of table type.
    
    Attributes:
        table_id: Unique identifier for this table
        document_id: Parent document ID
        page_number: Page number where table appears (1-indexed)
        table_index: Index of table on the page (0-indexed)
        table_bbox: Bounding box of entire table [x1, y1, x2, y2]
        cells: List of all cells with structural info
        header_rows: Indices of header rows (0-indexed)
        num_rows: Total number of rows
        num_cols: Total number of columns
        canonical_headers: Reconstructed header strings per column
        notes: Footer/footnote text if detected
        source: Extraction source (docling_structural, markdown, etc.)
        extractor_version: Version of the extractor used
        confidence_metrics: Quality metrics for the extraction
        classification: Optional table type classification
        classification_confidence: Confidence of classification
        raw_markdown: Original markdown if available (for debugging)
        metadata: Additional extraction metadata
    """
    
    table_id: str
    document_id: Optional[UUID] = None
    page_number: int = 1
    table_index: int = 0
    table_bbox: Optional[List[float]] = None
    cells: List[TableCellJSON] = field(default_factory=list)
    header_rows: List[int] = field(default_factory=list)
    num_rows: int = 0
    num_cols: int = 0
    canonical_headers: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    source: TableExtractionSource = TableExtractionSource.DOCLING_MARKDOWN
    extractor_version: str = "1.0.0"
    confidence_metrics: ConfidenceMetrics = field(default_factory=ConfidenceMetrics)
    classification: Optional[TableType] = None
    classification_confidence: float = 0.0
    raw_markdown: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate derived fields if not set."""
        if self.cells and self.num_rows == 0:
            self.num_rows = max(c.row for c in self.cells) + 1
        if self.cells and self.num_cols == 0:
            self.num_cols = max(c.col for c in self.cells) + 1
        if not self.header_rows and self.cells:
            # Default: first row is header
            self.header_rows = [0]
        if not self.canonical_headers and self.cells:
            self._reconstruct_headers()
        elif self.canonical_headers and self.cells:
            # Check if headers need reconstruction (they might be messy from old extraction)
            if self._headers_need_reconstruction():
                self._reconstruct_headers()
    
    def _headers_need_reconstruction(self) -> bool:
        """Check if headers need reconstruction (are messy/concatenated).
        
        Returns:
            True if headers appear to be concatenated and need cleaning
        """
        if not self.canonical_headers:
            return True
        
        # Check if any header is too long or contains concatenation patterns
        for header in self.canonical_headers:
            if not header:
                continue
            
            # Headers longer than 50 chars are likely concatenated
            if len(header) > 50:
                return True
            
            # Headers with multiple dots/periods are likely concatenated
            if header.count('.') > 2:
                return True
            
            # Headers with policy number patterns are likely concatenated
            import re
            if re.search(r'\d{2}-\d+-\s*[A-Z]-\d+', header):
                return True
            
            # Headers with organization names are likely concatenated
            if any(word in header.lower() for word in 
                   ['association', 'inc', 'total stated values', 'under policy']):
                if len(header) > 30:
                    return True
        
        return False
    
    def reconstruct_headers(self) -> None:
        """Force header reconstruction (public method).
        
        This can be called to rebuild headers from cells, useful when
        loading from database with potentially messy headers.
        """
        if self.cells:
            self._reconstruct_headers()
    
    def _reconstruct_headers(self) -> None:
        """Reconstruct canonical header strings from header cells.
        
        Handles multi-row headers intelligently:
        - For multi-row headers, prefers the last header row (usually contains actual column names)
        - Cleans up concatenated text from Docling (removes policy numbers, etc.)
        - Handles spanning cells properly
        """
        if not self.cells or not self.header_rows:
            return
        
        # Build header text per column
        headers = [""] * self.num_cols
        
        # Process header rows from top to bottom
        # For multi-row headers, later rows typically contain the actual column names
        sorted_header_rows = sorted(self.header_rows)
        
        for header_row_idx in sorted_header_rows:
            # Get all cells in this header row
            row_cells = [c for c in self.cells if c.row == header_row_idx]
            
            # Sort by column position
            row_cells.sort(key=lambda c: c.col)
            
            for cell in row_cells:
                cell_text = cell.text.strip()
                
                # Clean up concatenated text from Docling
                # Remove common patterns like policy numbers, document titles
                cell_text = self._clean_header_text(cell_text)
                
                if not cell_text:
                    continue
                
                # Apply text to all columns this cell spans
                for col_offset in range(cell.colspan):
                    col_idx = cell.col + col_offset
                    if col_idx < self.num_cols:
                        # For multi-row headers, prefer the last non-empty text
                        # This handles cases where first row has category headers,
                        # and last row has actual column names
                        if not headers[col_idx] or header_row_idx == sorted_header_rows[-1]:
                            # Use this text if column is empty or this is the last header row
                            headers[col_idx] = cell_text
                        elif cell_text and len(cell_text) < len(headers[col_idx]):
                            # Prefer shorter, more specific headers (usually column names)
                            # over longer category headers
                            if self._is_more_specific_header(cell_text, headers[col_idx]):
                                headers[col_idx] = cell_text
        
        # Clean up final headers
        self.canonical_headers = [self._clean_header_text(h) for h in headers]
    
    def _clean_header_text(self, text: str) -> str:
        """Clean header text by removing common concatenation artifacts.
        
        Args:
            text: Raw header text
            
        Returns:
            Cleaned header text
        """
        if not text:
            return ""
        
        import re
        
        # Remove common patterns that get concatenated:
        # - Policy numbers (e.g., "01-7590121387- S-02")
        # - Document titles (e.g., "Total Stated Values Under Policy")
        # - Organization names that span multiple header rows
        
        # Split on common separators and take the most relevant part
        # Common patterns: "Policy Title.Organization Name.Column Name"
        parts = re.split(r'[.\n]', text)
        
        # Filter out parts that look like policy numbers or document titles
        cleaned_parts = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Skip if it looks like a policy number
            if re.match(r'^\d{2}-\d+-\s*[A-Z]-\d+$', part):
                continue
            
            # Skip if it's a long document title
            if len(part) > 50 and any(word in part.lower() for word in 
                ['total stated values', 'under policy', 'association', 'inc']):
                continue
            
            # Keep shorter, more specific parts (likely column names)
            if len(part) < 50:
                cleaned_parts.append(part)
        
        # Return the last (most specific) part, or join if multiple relevant parts
        if cleaned_parts:
            # Prefer the shortest, most specific part
            return min(cleaned_parts, key=len) if len(cleaned_parts) > 1 else cleaned_parts[-1]
        
        # If all parts were filtered, return original text cleaned up
        return text.strip()
    
    def _is_more_specific_header(self, text1: str, text2: str) -> bool:
        """Check if text1 is a more specific (better) header than text2.
        
        Args:
            text1: First header text
            text2: Second header text
            
        Returns:
            True if text1 is more specific
        """
        # Shorter headers are often more specific (column names vs category headers)
        if len(text1) < len(text2):
            return True
        
        # Headers with common column keywords are more specific
        column_keywords = ['loc', 'bldg', 'building', 'contents', 'address', 'description', 
                          'value', 'limit', 'tiv', 'total', 'date', 'claim', 'policy']
        text1_lower = text1.lower()
        text2_lower = text2.lower()
        
        text1_keywords = sum(1 for kw in column_keywords if kw in text1_lower)
        text2_keywords = sum(1 for kw in column_keywords if kw in text2_lower)
        
        if text1_keywords > text2_keywords:
            return True
        
        return False
    
    def get_cell(self, row: int, col: int) -> Optional[TableCellJSON]:
        """Get cell at specified position.
        
        Args:
            row: Row index (0-based)
            col: Column index (0-based)
            
        Returns:
            TableCellJSON or None if not found
        """
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
            # Check if this cell spans to the requested position
            if (cell.row <= row < cell.row + cell.rowspan and
                cell.col <= col < cell.col + cell.colspan):
                return cell
        return None
    
    def get_row(self, row_index: int) -> List[str]:
        """Get all cell values in a row.
        
        Args:
            row_index: Row index (0-based)
            
        Returns:
            List of cell text values
        """
        row_values = [""] * self.num_cols
        for col in range(self.num_cols):
            cell = self.get_cell(row_index, col)
            if cell:
                row_values[col] = cell.text
        return row_values
    
    def get_data_rows(self) -> List[List[str]]:
        """Get all non-header rows as list of string lists.
        
        Returns:
            List of rows, each row is a list of cell values
        """
        data_rows = []
        for row_idx in range(self.num_rows):
            if row_idx not in self.header_rows:
                data_rows.append(self.get_row(row_idx))
        return data_rows
    
    def get_column(self, col_index: int) -> List[str]:
        """Get all cell values in a column.
        
        Args:
            col_index: Column index (0-based)
            
        Returns:
            List of cell text values
        """
        col_values = []
        for row in range(self.num_rows):
            cell = self.get_cell(row, col_index)
            col_values.append(cell.text if cell else "")
        return col_values
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "table_id": self.table_id,
            "document_id": str(self.document_id) if self.document_id else None,
            "page_number": self.page_number,
            "table_index": self.table_index,
            "table_bbox": self.table_bbox,
            "cells": [c.to_dict() for c in self.cells],
            "header_rows": self.header_rows,
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "canonical_headers": self.canonical_headers,
            "notes": self.notes,
            "source": self.source.value if isinstance(self.source, TableExtractionSource) else self.source,
            "extractor_version": self.extractor_version,
            "confidence_metrics": self.confidence_metrics.to_dict(),
            "classification": self.classification.value if self.classification else None,
            "classification_confidence": self.classification_confidence,
            "raw_markdown": self.raw_markdown,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableJSON":
        """Create from dictionary."""
        cells = [TableCellJSON.from_dict(c) for c in data.get("cells", [])]
        confidence_metrics = ConfidenceMetrics.from_dict(
            data.get("confidence_metrics", {})
        )
        
        source = data.get("source", "docling_markdown")
        if isinstance(source, str):
            try:
                source = TableExtractionSource(source)
            except ValueError:
                source = TableExtractionSource.DOCLING_MARKDOWN
        
        classification = data.get("classification")
        if classification and isinstance(classification, str):
            try:
                classification = TableType(classification)
            except ValueError:
                classification = TableType.UNKNOWN
        
        return cls(
            table_id=data.get("table_id", str(uuid4())),
            document_id=UUID(data["document_id"]) if data.get("document_id") else None,
            page_number=data.get("page_number", 1),
            table_index=data.get("table_index", 0),
            table_bbox=data.get("table_bbox"),
            cells=cells,
            header_rows=data.get("header_rows", [0] if cells else []),
            num_rows=data.get("num_rows", 0),
            num_cols=data.get("num_cols", 0),
            canonical_headers=data.get("canonical_headers", []),
            notes=data.get("notes"),
            source=source,
            extractor_version=data.get("extractor_version", "1.0.0"),
            confidence_metrics=confidence_metrics,
            classification=classification,
            classification_confidence=data.get("classification_confidence", 0.0),
            raw_markdown=data.get("raw_markdown"),
            metadata=data.get("metadata", {}),
        )
    
    def calculate_confidence_metrics(self) -> ConfidenceMetrics:
        """Calculate confidence metrics for this table.
        
        Returns:
            ConfidenceMetrics with calculated values
        """
        if not self.cells:
            return ConfidenceMetrics(overall=0.0)
        
        # Grid completeness: ratio of non-empty cells
        total_cells = self.num_rows * self.num_cols
        non_empty = sum(1 for c in self.cells if c.text.strip())
        grid_completeness = non_empty / total_cells if total_cells > 0 else 0.0
        
        # Column consistency: check if all rows have same column count
        row_col_counts = {}
        for cell in self.cells:
            if cell.row not in row_col_counts:
                row_col_counts[cell.row] = set()
            for col_offset in range(cell.colspan):
                row_col_counts[cell.row].add(cell.col + col_offset)
        
        if row_col_counts:
            col_counts = [len(cols) for cols in row_col_counts.values()]
            max_cols = max(col_counts)
            column_consistency = sum(c == max_cols for c in col_counts) / len(col_counts)
        else:
            column_consistency = 1.0
        
        # Span sanity: check for overlapping spans
        span_sanity = 1.0  # Assume good unless we find issues
        cell_coverage = {}
        for cell in self.cells:
            for row_offset in range(cell.rowspan):
                for col_offset in range(cell.colspan):
                    pos = (cell.row + row_offset, cell.col + col_offset)
                    if pos in cell_coverage:
                        span_sanity *= 0.8  # Penalty for overlap
                    cell_coverage[pos] = True
        
        # Numeric coherence: check if numeric-looking columns parse correctly
        numeric_coherence = 1.0
        for col in range(self.num_cols):
            col_values = [
                c.text for c in self.cells 
                if c.col == col and c.row not in self.header_rows
            ]
            if col_values:
                numeric_count = sum(
                    1 for v in col_values 
                    if self._looks_numeric(v)
                )
                if numeric_count > len(col_values) / 2:
                    # This looks like a numeric column
                    parseable = sum(
                        1 for v in col_values 
                        if self._can_parse_numeric(v)
                    )
                    col_coherence = parseable / len(col_values)
                    numeric_coherence = min(numeric_coherence, col_coherence)
        
        # Header likelihood: check if first row(s) look like headers
        header_likelihood = 1.0
        if self.cells:
            first_row_cells = [c for c in self.cells if c.row == 0]
            if first_row_cells:
                # Headers typically have more text, fewer numbers
                text_density = sum(
                    len(c.text) for c in first_row_cells
                ) / len(first_row_cells)
                numeric_ratio = sum(
                    1 for c in first_row_cells 
                    if self._looks_numeric(c.text)
                ) / len(first_row_cells)
                header_likelihood = min(1.0, text_density / 10) * (1 - numeric_ratio)
        
        # Overall score
        overall = (
            grid_completeness * 0.2 +
            column_consistency * 0.25 +
            span_sanity * 0.2 +
            numeric_coherence * 0.2 +
            header_likelihood * 0.15
        )
        
        return ConfidenceMetrics(
            overall=overall,
            grid_completeness=grid_completeness,
            column_consistency=column_consistency,
            span_sanity=span_sanity,
            numeric_coherence=numeric_coherence,
            header_likelihood=header_likelihood,
        )
    
    def _looks_numeric(self, value: str) -> bool:
        """Check if value looks like a number."""
        import re
        cleaned = re.sub(r'[$,\s%]', '', value.strip())
        return bool(re.match(r'^-?\d+\.?\d*$', cleaned))
    
    def _can_parse_numeric(self, value: str) -> bool:
        """Check if value can be parsed as a number."""
        import re
        cleaned = re.sub(r'[$,\s%]', '', value.strip())
        if not cleaned or cleaned in ['-', 'N/A', 'n/a', 'NA', 'na']:
            return True  # Empty/NA values are OK
        try:
            float(cleaned)
            return True
        except ValueError:
            return False


def create_table_id(document_id: Optional[UUID], page_number: int, table_index: int) -> str:
    """Create a deterministic table ID.
    
    Args:
        document_id: Document UUID
        page_number: Page number (1-indexed)
        table_index: Table index on page (0-indexed)
        
    Returns:
        Deterministic table ID string
    """
    doc_prefix = str(document_id)[:8] if document_id else "unknown"
    return f"tbl_{doc_prefix}_p{page_number}_t{table_index}"

