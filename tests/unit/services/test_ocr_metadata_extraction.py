import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from app.services.processed.services.ocr.ocr_service import OCRService

class TestOCRMetadataExtraction:
    """Tests for Docling metadata extraction logic."""

    @pytest.fixture
    def ocr_service(self):
        with patch('docling.document_converter.DocumentConverter'):
            return OCRService()

    def test_extract_rich_page_metadata_aggregates_correctly(self, ocr_service):
        """Test that _extract_rich_page_metadata aggregates blocks by page."""
        # Create mock Docling result
        mock_item1 = MagicMock()
        mock_item1.prov = [MagicMock(page_no=1)]
        mock_item1.label = 'heading'
        mock_item1.level = 1

        mock_item2 = MagicMock()
        mock_item2.prov = [MagicMock(page_no=1)]
        mock_item2.label = 'text'

        mock_item3 = MagicMock()
        mock_item3.prov = [MagicMock(page_no=2)]
        mock_item3.label = 'text'

        mock_table1 = MagicMock()
        mock_table1.prov = [MagicMock(page_no=2)]

        mock_doc = MagicMock()
        mock_doc.texts = [mock_item1, mock_item2, mock_item3]
        mock_doc.tables = [mock_table1]

        mock_result = MagicMock()
        mock_result.document = mock_doc

        metadata = ocr_service._extract_rich_page_metadata(mock_result)

        assert 1 in metadata
        assert metadata[1]["block_count"] == 2
        assert metadata[1]["text_block_count"] == 2
        assert metadata[1]["heading_levels"] == [1]
        assert metadata[1]["max_font_size"] == 24.0
        assert metadata[1]["structure_type"] == "standard"

        assert 2 in metadata
        assert metadata[2]["block_count"] == 2
        assert metadata[2]["text_block_count"] == 1
        assert metadata[2]["table_block_count"] == 1
        assert metadata[2]["structure_type"] == "mixed"

    def test_get_page_no_handles_various_prov_structures(self, ocr_service):
        """Test that _get_page_no handles different provenance formats."""
        # Format 1: list with page_no
        prov1 = MagicMock()
        prov1.page_no = 5
        del prov1.page # Ensure it doesn't have both
        item1 = MagicMock()
        item1.prov = [prov1]
        assert ocr_service._get_page_no(item1) == 5

        # Format 2: single object with page
        prov2 = MagicMock()
        del prov2.page_no # CRITICAL: Remove page_no so it falls through to page
        prov2.page = 10
        item2 = MagicMock()
        item2.prov = prov2
        assert ocr_service._get_page_no(item2) == 10

        # Format 3: missing prov
        item3 = MagicMock()
        item3.prov = None
        assert ocr_service._get_page_no(item3) == 1
