"""Docling-backed OCR service for document text extraction.

This service uses Docling as the primary document parser, providing:
- Layout-aware text extraction with structure preservation
- Native table detection and structured extraction
- Page-level extraction with coordinates and metadata
- Selective page processing
"""
import re
import time
from typing import Dict, Any, List, Optional
from uuid import UUID

from app.models.page_data import PageData
from app.utils.exceptions import OCRExtractionError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class DoclingOCRService:
    """OCR service implementation using Docling for document parsing.
    
    This service is the primary parser.It provides:
    - Layout-aware text extraction
    - Native table detection and structured extraction
    - Selective page processing based on page manifest
    - Rich metadata including coordinates and structure
    
    Attributes:
        converter: Docling DocumentConverter instance
    """
    
    # Regex pattern for detecting markdown tables
    TABLE_PATTERN = re.compile(
        r'\|[^\n]+\|[\s]*\n\|[-:\s|]+\|[\s]*\n(?:\|[^\n]+\|[\s]*\n)+',
        re.MULTILINE
    )
    
    def __init__(self):
        """Initialize DoclingOCRService with Docling converter."""
        try:
            from docling.document_converter import DocumentConverter
            self.converter = DocumentConverter()
            LOGGER.info(
                "Initialized DoclingOCRService",
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
            
            # Extract pages with table detection
            all_pages = self._extract_all_pages(transformed_pages, document_id)

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
    
    def _extract_all_pages(
        self, 
        transformed_pages: List[str], 
        document_id: UUID
    ) -> List[PageData]:
        """Extract data from all pages in the document.
        
        Args:
            transformed_pages: List of transformed pages with markdown
            document_id: Document ID for metadata
        
        Returns:
            List[PageData]: All extracted pages with table detection
        """
        pages = []
        
        for idx, page_content in enumerate(transformed_pages):
            page_number = idx + 1
            
            # Detect tables in markdown content
            has_tables = self._detect_tables_in_markdown(page_content)
            table_count = self._count_tables_in_markdown(page_content)
            
            # Build metadata
            metadata = {
                "source": "docling",
                "document_id": str(document_id),
                "has_tables": has_tables,
                "table_count": table_count
            }
            
            # Add table positions if tables exist
            if has_tables:
                table_info = self._extract_table_info(page_content)
                metadata["tables"] = table_info
            
            page_data = PageData(
                page_number=page_number,
                text=page_content,
                markdown=page_content,
                metadata=metadata
            )
            pages.append(page_data)

            if page_number == 12:
                LOGGER.info("Page content: %s", page_content)
                LOGGER.info("Page metadata: %s", metadata)
            
        return pages
    
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