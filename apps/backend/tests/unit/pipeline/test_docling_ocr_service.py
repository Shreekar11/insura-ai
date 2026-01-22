"""Unit tests for Docling-backed OCR service.

Tests the OCRService which:
- Uses Docling as the primary document parser
- Extracts layout-aware text and metadata
- Handles table extraction as structured data
- Provides page-level extraction with coordinates
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from typing import List

from app.models.page_data import PageData


class TestOCRService:
    """Tests for the Docling-backed OCR service."""
    
    @pytest.fixture
    def sample_pdf_path(self):
        """Sample PDF path for testing."""
        return "https://example.com/sample.pdf"
    
    @pytest.fixture
    def document_id(self):
        """Sample document ID."""
        return uuid4()
    
    @pytest.mark.asyncio
    async def test_extract_text_returns_page_data_list(
        self, sample_pdf_path, document_id
    ):
        """OCRService should return a list of PageData objects."""
        # Import will fail until we create the service
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            # Setup mock Docling converter
            mock_document = MagicMock()
            mock_document.pages = [MagicMock(), MagicMock(), MagicMock()]
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(sample_pdf_path, document_id)
            
            assert isinstance(result, list)
            assert all(isinstance(p, PageData) for p in result)
    
    @pytest.mark.asyncio
    async def test_extract_text_preserves_page_numbers(
        self, sample_pdf_path, document_id
    ):
        """Extracted pages should have correct 1-indexed page numbers."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_pages = []
            for i in range(5):
                page = MagicMock()
                page.text = f"Page {i+1} content"
                mock_pages.append(page)
            
            mock_document = MagicMock()
            mock_document.pages = mock_pages
            mock_document.export_to_markdown.return_value = "Full document markdown"
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(sample_pdf_path, document_id)
            
            # Page numbers should be 1-indexed
            page_numbers = [p.page_number for p in result]
            assert page_numbers == [1, 2, 3, 4, 5]
    
    @pytest.mark.asyncio
    async def test_extract_specific_pages_only(
        self, sample_pdf_path, document_id
    ):
        """Service should only extract specified pages when filter is provided."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        pages_to_extract = [1, 3, 5]
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_pages = []
            for i in range(10):
                page = MagicMock()
                page.text = f"Page {i+1} content"
                mock_pages.append(page)
            
            mock_document = MagicMock()
            mock_document.pages = mock_pages
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(
                sample_pdf_path, 
                document_id,
                pages_to_process=pages_to_extract
            )
            
            # Should only return the specified pages
            page_numbers = [p.page_number for p in result]
            assert page_numbers == pages_to_extract
            assert len(result) == 3
    
    @pytest.mark.asyncio
    async def test_extract_text_includes_markdown(
        self, sample_pdf_path, document_id
    ):
        """Extracted pages should include markdown content when available."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_page = MagicMock()
            mock_page.text = "Plain text content"
            
            mock_document = MagicMock()
            mock_document.pages = [mock_page]
            mock_document.export_to_markdown.return_value = "# Heading\n\nMarkdown content"
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(sample_pdf_path, document_id)
            
            # At least one page should have markdown
            assert any(p.markdown is not None for p in result)
    
    @pytest.mark.asyncio
    async def test_extract_tables_as_structured_data(
        self, sample_pdf_path, document_id
    ):
        """Tables should be extracted as structured data in metadata."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            # Create a mock page with table
            mock_table = MagicMock()
            mock_table.to_dict.return_value = {
                "headers": ["Column A", "Column B"],
                "rows": [["Value 1", "Value 2"], ["Value 3", "Value 4"]]
            }
            
            mock_page = MagicMock()
            mock_page.text = "Page with table"
            mock_page.tables = [mock_table]
            
            mock_document = MagicMock()
            mock_document.pages = [mock_page]
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(sample_pdf_path, document_id)
            
            # Table data should be in metadata
            assert len(result) == 1
            page = result[0]
            assert "tables" in page.metadata
            assert len(page.metadata["tables"]) == 1
    
    @pytest.mark.asyncio
    async def test_handles_empty_pages(
        self, sample_pdf_path, document_id
    ):
        """Service should handle pages with no text gracefully."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_page = MagicMock()
            mock_page.text = ""  # Empty page
            
            mock_document = MagicMock()
            mock_document.pages = [mock_page]
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(sample_pdf_path, document_id)
            
            # Should return the page even if empty
            assert len(result) == 1
            assert result[0].text == ""
    
    @pytest.mark.asyncio
    async def test_includes_page_metadata(
        self, sample_pdf_path, document_id
    ):
        """Extracted pages should include metadata (coordinates, etc.)."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_page = MagicMock()
            mock_page.text = "Page content"
            mock_page.width = 612
            mock_page.height = 792
            
            mock_document = MagicMock()
            mock_document.pages = [mock_page]
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(sample_pdf_path, document_id)
            
            assert len(result) == 1
            page = result[0]
            assert page.metadata is not None
            # Should include page dimensions
            assert "width" in page.metadata or "page_width" in page.metadata
            assert "height" in page.metadata or "page_height" in page.metadata


class TestOCRServiceErrorHandling:
    """Tests for error handling in OCRService."""
    
    @pytest.fixture
    def sample_pdf_path(self):
        return "https://example.com/sample.pdf"
    
    @pytest.fixture
    def document_id(self):
        return uuid4()
    
    @pytest.mark.asyncio
    async def test_handles_conversion_error(
        self, sample_pdf_path, document_id
    ):
        """Service should raise appropriate error when conversion fails."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        from app.core.exceptions import OCRExtractionError
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_converter = MagicMock()
            mock_converter.convert.side_effect = Exception("Conversion failed")
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            
            with pytest.raises(OCRExtractionError):
                await service.extract_pages(sample_pdf_path, document_id)
    
    @pytest.mark.asyncio
    async def test_handles_invalid_page_numbers(
        self, sample_pdf_path, document_id
    ):
        """Service should handle invalid page numbers gracefully."""
        from app.services.processed.services.ocr.ocr_service import OCRService
        
        # Request pages that don't exist
        pages_to_extract = [1, 100, 200]  # Only page 1 exists
        
        with patch('docling.document_converter.DocumentConverter') as mock_converter_class:
            mock_page = MagicMock()
            mock_page.text = "Page 1 content"
            
            mock_document = MagicMock()
            mock_document.pages = [mock_page]  # Only 1 page
            
            mock_result = MagicMock()
            mock_result.document = mock_document
            
            mock_converter = MagicMock()
            mock_converter.convert.return_value = mock_result
            mock_converter_class.return_value = mock_converter
            
            service = OCRService()
            result = await service.extract_pages(
                sample_pdf_path, 
                document_id,
                pages_to_process=pages_to_extract
            )
            
            # Should only return the valid page
            assert len(result) == 1
            assert result[0].page_number == 1


class TestOCRServiceIntegration:
    """Integration-style tests for OCRService with OCRExtractionPipeline."""
    
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_pipeline_uses_docling_service(self, mock_session):
        """OCRExtractionPipeline should use OCRService for extraction."""
        from app.pipeline.ocr_extraction import OCRExtractionPipeline
        
        document_id = uuid4()
        document_url = "https://example.com/test.pdf"
        
        with patch('app.pipeline.ocr_extraction.OCRService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.extract_pages = AsyncMock(return_value=[
                PageData(page_number=1, text="Page 1"),
                PageData(page_number=2, text="Page 2"),
            ])
            mock_service_class.return_value = mock_service
            
            with patch.object(OCRExtractionPipeline, '__init__', lambda x, y: None):
                pipeline = OCRExtractionPipeline(mock_session)
                pipeline.session = mock_session
                pipeline.doc_repo = MagicMock()
                pipeline.doc_repo.store_pages = AsyncMock()
                pipeline.docling_service = mock_service
                
                # This test expects the pipeline to use OCRService
                # Will fail until we implement the integration
                result = await pipeline.extract_and_store_pages(
                    document_id,
                    document_url
                )
                
                # Verify OCRService was used
                mock_service.extract_pages.assert_called_once()

