"""Unit tests for Delta Reprocessing."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import hashlib

from app.services.normalization.normalization_service import NormalizationService
from app.repositories.normalization_repository import NormalizationRepository
from app.models.page_data import PageData


class TestDeltaReprocessing:
    """Tests for delta reprocessing logic."""
    
    @pytest.fixture
    def mock_normalization_repo(self):
        return AsyncMock(spec=NormalizationRepository)
        
    @pytest.fixture
    def normalization_service(self, mock_normalization_repo):
        service = NormalizationService(
            chunk_repository=AsyncMock(),
            normalization_repository=mock_normalization_repo,
            classification_repository=AsyncMock(),
        )
        # Mock other dependencies
        service.chunking_service = MagicMock()
        service.llm_normalizer = AsyncMock()
        service.semantic_normalizer = MagicMock()
        service.entity_extractor = AsyncMock()
        service.entity_resolver = AsyncMock()
        class MockClassificationService:
            def aggregate_signals(self, *args, **kwargs):
                return {
                    "classified_type": "policy",
                    "confidence": 0.95,
                    "document_type": "policy",
                    "method": "aggregate",
                    "all_scores": {"policy": 0.95},
                    "chunks_used": 1,
                    "fallback_used": False,
                    "decision_details": {}
                }
            async def create_classification_signal(self, *args, **kwargs):
                pass
                
        service.classification_service = MockClassificationService()
        
        service.chunking_service.chunk_document.return_value = [
            MagicMock(
                text="chunk text",
                metadata=MagicMock(
                    page_number=1,
                    chunk_index=0,
                    token_count=10,
                    section_name="section",
                    stable_chunk_id="doc_1_p1_c0",
                    section_type="policy",
                    subsection_type="header"
                )
            )
        ]
        service.llm_normalizer.normalize_with_signals.return_value = {
            "normalized_text": "normalized text",
            "signals": [],
            "confidence": 0.9
        }
        service.semantic_normalizer.normalize_text_with_fields.return_value = {
            "normalized_text": "normalized text",
            "extracted_fields": {}
        }
        service.chunk_repository.create_chunk.return_value = MagicMock(id=uuid4())
        
        return service

    async def test_skip_unchanged_chunks(self, normalization_service, mock_normalization_repo):
        """Test skipping entity extraction for unchanged chunks."""
        # Setup
        mock_normalization_repo.check_content_changed.return_value = False
        
        # Execute
        pages = [PageData(page_number=1, text="raw text")]
        await normalization_service.normalize_and_classify_pages(pages, uuid4())
        
        # Verify
        # Should check content changed
        mock_normalization_repo.check_content_changed.assert_called_once()
        
        # Should NOT call entity extractor
        normalization_service.entity_extractor.extract.assert_not_called()
        
        # Should update normalized chunk with pipeline_run_id only
        mock_normalization_repo.update_normalized_chunk.assert_called_once()
        call_kwargs = mock_normalization_repo.update_normalized_chunk.call_args.kwargs
        assert "pipeline_run_id" in call_kwargs
        assert "normalized_text" not in call_kwargs  # Should not update text
        
        # Should NOT create new normalized chunk
        mock_normalization_repo.create_normalized_chunk.assert_not_called()

    async def test_process_changed_chunks(self, normalization_service, mock_normalization_repo):
        """Test processing chunks when content changed."""
        # Setup
        mock_normalization_repo.check_content_changed.return_value = True
        mock_normalization_repo.get_normalized_chunk_by_id.return_value = MagicMock() # Existing chunk
        
        # Execute
        pages = [PageData(page_number=1, text="raw text")]
        await normalization_service.normalize_and_classify_pages(pages, uuid4())
        
        # Verify
        # Should check content changed
        mock_normalization_repo.check_content_changed.assert_called_once()
        
        # Should call entity extractor
        normalization_service.entity_extractor.extract.assert_called_once()
        
        # Should update normalized chunk with all fields
        mock_normalization_repo.update_normalized_chunk.assert_called_once()
        call_kwargs = mock_normalization_repo.update_normalized_chunk.call_args.kwargs
        assert "normalized_text" in call_kwargs
        assert "entities" in call_kwargs
        
    async def test_process_new_chunks(self, normalization_service, mock_normalization_repo):
        """Test processing new chunks (no existing normalized chunk)."""
        # Setup
        mock_normalization_repo.check_content_changed.return_value = True
        mock_normalization_repo.get_normalized_chunk_by_id.return_value = None # No existing chunk
        
        # Execute
        pages = [PageData(page_number=1, text="raw text")]
        await normalization_service.normalize_and_classify_pages(pages, uuid4())
        
        # Verify
        # Should call entity extractor
        normalization_service.entity_extractor.extract.assert_called_once()
        
        # Should create new normalized chunk
        mock_normalization_repo.create_normalized_chunk.assert_called_once()
        mock_normalization_repo.update_normalized_chunk.assert_not_called()
