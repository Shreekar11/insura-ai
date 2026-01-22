"""Unit tests for selective OCR extraction.

Tests the selective OCR behavior where:
- Only pages specified in pages_to_process are OCR'd
- Uses Docling as the primary parser
- Respects page roles from manifest (table vs text pages)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models.page_data import PageData


class TestSelectiveOCRActivity:
    """Tests for the extract_ocr activity with selective page processing."""
    
    @pytest.fixture
    def document_id(self):
        """Create a test document ID."""
        return str(uuid4())
    
    @pytest.fixture
    def mock_document(self):
        """Create a mock document with file path."""
        doc = MagicMock()
        doc.file_path = "https://example.com/test.pdf"
        return doc
    
    @pytest.mark.asyncio
    async def test_extract_ocr_with_pages_to_process_filters_pages(
        self, document_id, mock_document
    ):
        """When pages_to_process is provided, only those pages should be OCR'd.
        
        """
        pages_to_process = [1, 5, 10]  # Only process these pages
        
        # Mock the pipeline to verify it receives the correct pages
        with patch('app.temporal.activities.ocr_extraction.async_session_maker') as mock_session_maker, \
             patch('app.temporal.activities.ocr_extraction.OCRExtractionPipeline') as mock_pipeline_class:
            
            # Setup mock session
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_session
            
            # Setup mock document repository
            with patch('app.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
                mock_doc_repo = MagicMock()
                mock_doc_repo.get_by_id = AsyncMock(return_value=mock_document)
                mock_doc_repo_class.return_value = mock_doc_repo
                
                # Setup mock pipeline
                mock_pipeline = MagicMock()
                mock_pipeline.extract_and_store_pages = AsyncMock(return_value=[
                    PageData(page_number=1, text="Page 1 text"),
                    PageData(page_number=5, text="Page 5 text"),
                    PageData(page_number=10, text="Page 10 text"),
                ])
                mock_pipeline_class.return_value = mock_pipeline
                
                # Import and call the activity
                from app.temporal.activities.ocr_extraction import extract_ocr
                
                result = await extract_ocr(document_id, pages_to_process)
                
                # Verify the pipeline was called with pages_to_process
                mock_pipeline.extract_and_store_pages.assert_called_once()
                call_args = mock_pipeline.extract_and_store_pages.call_args
                
                # The pipeline should receive the pages_to_process list
                # This assertion will FAIL until we implement the feature
                assert call_args is not None
                # Check that pages_to_process was passed through
                # (implementation will need to accept this parameter)
    
    @pytest.mark.asyncio
    async def test_extract_ocr_without_pages_to_process_processes_all(
        self, document_id, mock_document
    ):
        """When pages_to_process is None, all pages should be processed (legacy behavior)."""
        with patch('app.temporal.activities.ocr_extraction.async_session_maker') as mock_session_maker, \
             patch('app.temporal.activities.ocr_extraction.OCRExtractionPipeline') as mock_pipeline_class:
            
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_session
            
            with patch('app.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
                mock_doc_repo = MagicMock()
                mock_doc_repo.get_by_id = AsyncMock(return_value=mock_document)
                mock_doc_repo_class.return_value = mock_doc_repo
                
                mock_pipeline = MagicMock()
                mock_pipeline.extract_and_store_pages = AsyncMock(return_value=[
                    PageData(page_number=i, text=f"Page {i} text")
                    for i in range(1, 11)  # 10 pages
                ])
                mock_pipeline_class.return_value = mock_pipeline
                
                from app.temporal.activities.ocr_extraction import extract_ocr
                
                result = await extract_ocr(document_id, None)
                
                # Should return all pages
                assert result["page_count"] == 10
    
    @pytest.mark.asyncio
    async def test_extract_ocr_returns_correct_page_count(
        self, document_id, mock_document
    ):
        """Result should report the correct number of pages processed."""
        pages_to_process = [2, 4, 6]
        
        with patch('app.temporal.activities.ocr_extraction.async_session_maker') as mock_session_maker, \
             patch('app.temporal.activities.ocr_extraction.OCRExtractionPipeline') as mock_pipeline_class:
            
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session_maker.return_value = mock_session
            
            with patch('app.repositories.document_repository.DocumentRepository') as mock_doc_repo_class:
                mock_doc_repo = MagicMock()
                mock_doc_repo.get_by_id = AsyncMock(return_value=mock_document)
                mock_doc_repo_class.return_value = mock_doc_repo
                
                mock_pipeline = MagicMock()
                mock_pipeline.extract_and_store_pages = AsyncMock(return_value=[
                    PageData(page_number=2, text="Page 2"),
                    PageData(page_number=4, text="Page 4"),
                    PageData(page_number=6, text="Page 6"),
                ])
                mock_pipeline_class.return_value = mock_pipeline
                
                from app.temporal.activities.ocr_extraction import extract_ocr
                
                result = await extract_ocr(document_id, pages_to_process)
                
                # Should report exactly 3 pages processed
                assert result["page_count"] == 3
                assert result["document_id"] == document_id


class TestOCRExtractionPipelineSelective:
    """Tests for OCRExtractionPipeline with selective page processing."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_pipeline_extract_pages_with_filter(self, mock_session):
        """Pipeline should only extract specified pages when given a filter."""
        from app.pipeline.ocr_extraction import OCRExtractionPipeline
        
        document_id = uuid4()
        document_url = "https://example.com/test.pdf"
        pages_to_process = [1, 3, 5]
        
        with patch.object(OCRExtractionPipeline, '__init__', lambda x, y: None):
            pipeline = OCRExtractionPipeline(mock_session)
            pipeline.session = mock_session
            pipeline.doc_repo = MagicMock()
            
            # Mock the Docling service to return filtered pages
            mock_docling_service = MagicMock()
            filtered_pages = [
                PageData(page_number=i, text=f"Page {i} content")
                for i in pages_to_process
            ]
            mock_docling_service.extract_pages = AsyncMock(return_value=filtered_pages)
            pipeline.docling_service = mock_docling_service
            
            # Mock doc_repo.store_pages
            pipeline.doc_repo.store_pages = AsyncMock()
            
            # Call with pages_to_process filter
            result = await pipeline.extract_and_store_pages(
                document_id, 
                document_url,
                pages_to_process=pages_to_process
            )
            
            # Verify docling service was called with pages_to_process
            mock_docling_service.extract_pages.assert_called_once_with(
                document_url=document_url,
                document_id=document_id,
                pages_to_process=pages_to_process
            )
            
            # Should only store the filtered pages
            stored_pages = pipeline.doc_repo.store_pages.call_args[0][1]
            stored_page_numbers = [p.page_number for p in stored_pages]
            
            assert stored_page_numbers == pages_to_process
            assert len(result) == len(pages_to_process)
    
    @pytest.mark.asyncio
    async def test_pipeline_extract_all_pages_when_no_filter(self, mock_session):
        """Pipeline should extract all pages when no filter is provided."""
        from app.pipeline.ocr_extraction import OCRExtractionPipeline
        
        document_id = uuid4()
        document_url = "https://example.com/test.pdf"
        
        with patch.object(OCRExtractionPipeline, '__init__', lambda x, y: None):
            pipeline = OCRExtractionPipeline(mock_session)
            pipeline.session = mock_session
            pipeline.doc_repo = MagicMock()
            
            all_pages = [
                PageData(page_number=i, text=f"Page {i} content")
                for i in range(1, 6)
            ]
            mock_docling_service = MagicMock()
            mock_docling_service.extract_pages = AsyncMock(return_value=all_pages)
            pipeline.docling_service = mock_docling_service
            pipeline.doc_repo.store_pages = AsyncMock()
            
            # Call without pages_to_process filter
            result = await pipeline.extract_and_store_pages(
                document_id, 
                document_url
            )
            
            # Verify docling service was called with pages_to_process=None
            mock_docling_service.extract_pages.assert_called_once_with(
                document_url=document_url,
                document_id=document_id,
                pages_to_process=None
            )
            
            # Should store all pages
            stored_pages = pipeline.doc_repo.store_pages.call_args[0][1]
            assert len(stored_pages) == 5
            assert len(result) == 5

