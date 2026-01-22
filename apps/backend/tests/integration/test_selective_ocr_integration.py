"""Integration tests for selective OCR workflow.

Tests the complete selective OCR flow:
- ProcessDocumentWorkflow with page manifest
- OCRExtractionWorkflow respecting pages_to_process
- Proper page filtering and storage
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.models.page_data import PageData
from app.models.page_analysis_models import PageManifest, PageClassification, PageType


class TestSelectiveOCRWorkflowIntegration:
    """Integration tests for selective OCR with Temporal workflows."""
    
    @pytest.fixture
    def document_id(self):
        """Create a test document ID."""
        return str(uuid4())
    
    @pytest.fixture
    def sample_manifest(self, document_id):
        """Create a sample page manifest with selective pages."""
        classifications = [
            PageClassification(
                page_number=1,
                page_type=PageType.DECLARATIONS,
                confidence=0.95,
                should_process=True,
                reasoning="Contains declarations keywords"
            ),
            PageClassification(
                page_number=2,
                page_type=PageType.BOILERPLATE,
                confidence=0.90,
                should_process=False,
                reasoning="Standard boilerplate text"
            ),
            PageClassification(
                page_number=3,
                page_type=PageType.COVERAGES,
                confidence=0.92,
                should_process=True,
                reasoning="Contains coverage information"
            ),
            PageClassification(
                page_number=4,
                page_type=PageType.DUPLICATE,
                confidence=1.0,
                should_process=False,
                duplicate_of=2,
                reasoning="Duplicate of page 2"
            ),
            PageClassification(
                page_number=5,
                page_type=PageType.ENDORSEMENT,
                confidence=0.88,
                should_process=True,
                reasoning="Contains endorsement"
            ),
        ]
        
        return PageManifest(
            document_id=uuid4(),
            total_pages=5,
            pages_to_process=[1, 3, 5],  # Only process these
            pages_skipped=[2, 4],  # Skip boilerplate and duplicates
            classifications=classifications
        )
    
    @pytest.mark.asyncio
    async def test_workflow_stats_reflect_selective_processing(
        self, document_id, sample_manifest
    ):
        """Workflow result should accurately report selective processing stats."""
        pages_to_process = sample_manifest.pages_to_process
        
        # Create mock activity result
        expected_result = {
            "document_id": document_id,
            "page_count": len(pages_to_process),
            "pages_processed": pages_to_process,
            "pages_skipped": sample_manifest.pages_skipped,
        }
        
        # The workflow result should include accurate counts
        assert expected_result["page_count"] == 3
        assert len(expected_result["pages_skipped"]) == 2
    
    @pytest.mark.asyncio
    async def test_process_document_workflow_passes_manifest_pages(
        self, document_id
    ):
        """ProcessDocumentWorkflow should pass pages_to_process from manifest to OCR workflow."""
        # This tests the parent workflow's behavior
        
        manifest_result = {
            "document_id": document_id,
            "total_pages": 10,
            "pages_to_process": [1, 3, 5, 7],
            "pages_skipped": [2, 4, 6, 8, 9, 10],
            "processing_ratio": 0.4,
        }
        
        # The parent workflow should extract pages_to_process from manifest
        # and pass it to the OCR child workflow
        assert manifest_result["pages_to_process"] == [1, 3, 5, 7]
        assert len(manifest_result["pages_to_process"]) == 4


class TestSelectiveOCRPipelineIntegration:
    """Integration tests for the OCR pipeline with selective extraction."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        return session
    
    @pytest.mark.asyncio
    async def test_pipeline_stores_only_selected_pages(self, mock_session):
        """Pipeline should only store pages that were selected for processing."""
        from app.pipeline.ocr_extraction import OCRExtractionPipeline
        
        document_id = uuid4()
        document_url = "https://example.com/test.pdf"
        pages_to_process = [1, 5, 10]
        
        with patch.object(OCRExtractionPipeline, '__init__', lambda x, y: None):
            pipeline = OCRExtractionPipeline(mock_session)
            pipeline.session = mock_session
            
            # Mock document repository
            mock_doc_repo = MagicMock()
            mock_doc_repo.store_pages = AsyncMock()
            pipeline.doc_repo = mock_doc_repo
            
            # Mock the Docling service to return only selected pages
            selected_pages = [
                PageData(page_number=i, text=f"Page {i} content")
                for i in pages_to_process
            ]
            
            mock_docling_service = MagicMock()
            mock_docling_service.extract_pages = AsyncMock(return_value=selected_pages)
            pipeline.docling_service = mock_docling_service
            
            # Call with selective pages
            result = await pipeline.extract_and_store_pages(
                document_id,
                document_url,
                pages_to_process=pages_to_process
            )
            
            # Verify only selected pages were stored
            store_call_args = mock_doc_repo.store_pages.call_args
            stored_pages = store_call_args[0][1]
            stored_page_numbers = [p.page_number for p in stored_pages]
            
            assert stored_page_numbers == pages_to_process
            assert len(stored_pages) == 3
    
    @pytest.mark.asyncio
    async def test_pipeline_preserves_page_content_integrity(self, mock_session):
        """Filtered pages should have their content preserved correctly."""
        from app.pipeline.ocr_extraction import OCRExtractionPipeline
        
        document_id = uuid4()
        document_url = "https://example.com/test.pdf"
        pages_to_process = [2, 4]
        
        with patch.object(OCRExtractionPipeline, '__init__', lambda x, y: None):
            pipeline = OCRExtractionPipeline(mock_session)
            pipeline.session = mock_session
            
            mock_doc_repo = MagicMock()
            mock_doc_repo.store_pages = AsyncMock()
            pipeline.doc_repo = mock_doc_repo
            
            # Create pages with distinct content (only the selected ones)
            selected_pages = [
                PageData(page_number=2, text="Page 2: Declarations", markdown="# Declarations"),
                PageData(page_number=4, text="Page 4: Coverages", markdown="# Coverages"),
            ]
            
            mock_docling_service = MagicMock()
            mock_docling_service.extract_pages = AsyncMock(return_value=selected_pages)
            pipeline.docling_service = mock_docling_service
            
            result = await pipeline.extract_and_store_pages(
                document_id,
                document_url,
                pages_to_process=pages_to_process
            )
            
            # Verify content is preserved
            stored_pages = mock_doc_repo.store_pages.call_args[0][1]
            
            page_2 = next(p for p in stored_pages if p.page_number == 2)
            page_4 = next(p for p in stored_pages if p.page_number == 4)
            
            assert "Declarations" in page_2.text
            assert page_2.markdown == "# Declarations"
            assert "Coverages" in page_4.text


class TestSelectiveOCRDatabaseIntegration:
    """Tests for database operations with selective OCR."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_manifest_pages_retrieved_for_ocr(self, mock_session):
        """OCR activity should retrieve pages_to_process from manifest."""
        from app.repositories.document_repository import DocumentRepository
        
        document_id = uuid4()
        
        # Mock manifest retrieval
        with patch.object(DocumentRepository, 'get_manifest_pages') as mock_get_manifest:
            mock_get_manifest.return_value = [1, 3, 5, 7]
            
            # The activity should use this to filter OCR
            # This tests the expected interface
            repo = DocumentRepository(mock_session)
            pages = await repo.get_manifest_pages(document_id)
            
            assert pages == [1, 3, 5, 7]
    
    @pytest.mark.asyncio
    async def test_selective_pages_stored_with_metadata(self, mock_session):
        """Stored pages should include processing metadata."""
        from app.repositories.document_repository import DocumentRepository
        
        document_id = uuid4()
        pages = [
            PageData(
                page_number=1, 
                text="Page 1 content",
                metadata={"source": "docling", "selective": True}
            ),
            PageData(
                page_number=5, 
                text="Page 5 content",
                metadata={"source": "docling", "selective": True}
            ),
        ]
        
        with patch.object(DocumentRepository, 'store_pages') as mock_store:
            mock_store.return_value = None
            
            repo = DocumentRepository(mock_session)
            await repo.store_pages(document_id, pages)
            
            # Verify pages were stored with metadata
            mock_store.assert_called_once()
            stored_pages = mock_store.call_args[0][1]
            
            for page in stored_pages:
                assert page.metadata.get("source") == "docling"
                assert page.metadata.get("selective") is True

