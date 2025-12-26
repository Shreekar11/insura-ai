"""Unit tests for HybridChunkingService.

Tests the v2 hybrid chunking implementation including:
- Section detection from text content
- Hybrid chunk creation with metadata
- Section super-chunk building
- Token-aware splitting
"""

import pytest
from uuid import uuid4

from app.services.chunking.hybrid_chunking_service import HybridChunkingService
from app.services.chunking.hybrid_models import (
    SectionType,
    ChunkRole,
    HybridChunk,
    HybridChunkMetadata,
    SectionSuperChunk,
    ChunkingResult,
)
from app.models.page_data import PageData


class TestHybridChunkingService:
    """Test suite for HybridChunkingService."""
    
    @pytest.fixture
    def service(self):
        """Create HybridChunkingService instance."""
        return HybridChunkingService(
            max_tokens=1500,
            overlap_tokens=50,
        )
    
    @pytest.fixture
    def sample_pages(self):
        """Create sample insurance document pages."""
        return [
            PageData(
                page_number=1,
                text="DECLARATIONS\n\nPolicy Number: POL-2024-001\nNamed Insured: ABC Manufacturing LLC\nEffective Date: 01/01/2024\nExpiration Date: 01/01/2025",
                markdown="# DECLARATIONS\n\n**Policy Number:** POL-2024-001\n**Named Insured:** ABC Manufacturing LLC",
                metadata={"has_tables": False},
            ),
            PageData(
                page_number=2,
                text="COVERAGES\n\nCOVERAGE A - BUILDING\nLimit: $5,000,000\nDeductible: $5,000\n\nCOVERAGE B - CONTENTS\nLimit: $1,000,000\nDeductible: $2,500",
                markdown="# COVERAGES\n\n## Coverage A - Building\n- Limit: $5,000,000\n- Deductible: $5,000",
                metadata={"has_tables": False},
            ),
            PageData(
                page_number=3,
                text="CONDITIONS\n\nDUTIES IN THE EVENT OF LOSS\nYou must notify us promptly of any loss or damage.",
                markdown="# CONDITIONS\n\n## Duties in the Event of Loss",
                metadata={"has_tables": False},
            ),
            PageData(
                page_number=4,
                text="EXCLUSIONS\n\nWe do not cover loss or damage caused by:\n1. War\n2. Nuclear hazard\n3. Intentional acts",
                markdown="# EXCLUSIONS",
                metadata={"has_tables": False},
            ),
        ]
    
    @pytest.fixture
    def table_page(self):
        """Create page with table content."""
        return PageData(
            page_number=5,
            text="SCHEDULE OF VALUES\n\n| Location | Address | Building Value | Contents Value |\n|----------|---------|----------------|----------------|\n| 1 | 123 Main St | $2,000,000 | $500,000 |",
            markdown="# SCHEDULE OF VALUES\n\n| Location | Address | Building Value | Contents Value |\n|----------|---------|----------------|----------------|\n| 1 | 123 Main St | $2,000,000 | $500,000 |",
            metadata={"has_tables": True, "table_count": 1},
        )
    
    def test_init(self, service):
        """Test service initialization."""
        assert service.max_tokens == 1500
        assert service.overlap_tokens == 50
        assert service.token_counter is not None
    
    def test_chunk_empty_pages(self, service):
        """Test chunking with empty pages list."""
        result = service.chunk_pages([])
        
        assert isinstance(result, ChunkingResult)
        assert len(result.chunks) == 0
        assert len(result.super_chunks) == 0
        assert result.total_tokens == 0
    
    def test_chunk_pages_creates_chunks(self, service, sample_pages):
        """Test that chunking creates proper chunks."""
        document_id = uuid4()
        result = service.chunk_pages(sample_pages, document_id)
        
        assert isinstance(result, ChunkingResult)
        assert len(result.chunks) >= len(sample_pages)
        assert result.total_tokens > 0
        assert result.total_pages == len(sample_pages)
    
    def test_chunk_pages_detects_sections(self, service, sample_pages):
        """Test that section types are correctly detected."""
        result = service.chunk_pages(sample_pages)
        
        # Check that different sections are detected
        section_types = set(
            c.metadata.section_type for c in result.chunks 
            if c.metadata.section_type
        )
        
        assert SectionType.DECLARATIONS in section_types
        assert SectionType.COVERAGES in section_types
        assert SectionType.CONDITIONS in section_types
        assert SectionType.EXCLUSIONS in section_types
    
    def test_chunk_pages_creates_super_chunks(self, service, sample_pages):
        """Test that super-chunks are created."""
        result = service.chunk_pages(sample_pages)
        
        assert len(result.super_chunks) > 0
        
        # Each super-chunk should have chunks
        for sc in result.super_chunks:
            assert len(sc.chunks) > 0
            assert sc.section_type is not None
            assert sc.total_tokens > 0
    
    def test_chunk_metadata_complete(self, service, sample_pages):
        """Test that chunk metadata is complete."""
        document_id = uuid4()
        result = service.chunk_pages(sample_pages, document_id)
        
        for chunk in result.chunks:
            assert chunk.metadata.document_id == document_id
            assert chunk.metadata.page_number >= 1
            assert chunk.metadata.token_count > 0
            assert chunk.metadata.stable_chunk_id is not None
    
    def test_contextualized_text_created(self, service, sample_pages):
        """Test that contextualized text is created for chunks."""
        result = service.chunk_pages(sample_pages)
        
        for chunk in result.chunks:
            # Contextualized text should include context header
            if chunk.metadata.context_header:
                assert chunk.contextualized_text is not None
                assert chunk.metadata.context_header in chunk.contextualized_text
    
    def test_table_detection(self, service, table_page):
        """Test that tables are detected in pages."""
        result = service.chunk_pages([table_page])
        
        assert len(result.chunks) >= 1
        
        # Find chunk with table
        table_chunks = [c for c in result.chunks if c.metadata.has_tables]
        assert len(table_chunks) > 0
        
        # Check chunk role
        for tc in table_chunks:
            assert tc.metadata.chunk_role in [ChunkRole.TABLE, ChunkRole.MIXED]
    
    def test_sov_section_detected(self, service, table_page):
        """Test that SOV section is detected."""
        result = service.chunk_pages([table_page])
        
        sov_chunks = [
            c for c in result.chunks 
            if c.metadata.section_type == SectionType.SCHEDULE_OF_VALUES
        ]
        
        assert len(sov_chunks) > 0
    
    def test_section_map_populated(self, service, sample_pages):
        """Test that section map is populated."""
        result = service.chunk_pages(sample_pages)
        
        assert len(result.section_map) > 0
        
        # Should have counts for different sections
        for section, count in result.section_map.items():
            assert count > 0
    
    def test_statistics_calculated(self, service, sample_pages):
        """Test that statistics are calculated."""
        result = service.chunk_pages(sample_pages)
        
        assert "avg_tokens_per_chunk" in result.statistics
        assert "max_chunk_tokens" in result.statistics
        assert "min_chunk_tokens" in result.statistics
        assert result.statistics["avg_tokens_per_chunk"] > 0
    
    def test_super_chunk_priority(self, service, sample_pages):
        """Test that super-chunks are sorted by priority."""
        result = service.chunk_pages(sample_pages)
        
        priorities = [sc.processing_priority for sc in result.super_chunks]
        
        # Should be sorted by priority
        assert priorities == sorted(priorities)
    
    def test_llm_required_super_chunks(self, service, sample_pages, table_page):
        """Test filtering of LLM-required super-chunks."""
        all_pages = sample_pages + [table_page]
        result = service.chunk_pages(all_pages)
        
        llm_required = result.get_llm_required_super_chunks()
        table_only = result.get_table_only_super_chunks()
        
        # Declarations, Coverages, Conditions, Exclusions should require LLM
        # SOV should be table-only
        assert len(llm_required) >= 4
        
        # Check that SOV is in table_only
        sov_in_table_only = any(
            sc.section_type == SectionType.SCHEDULE_OF_VALUES 
            for sc in table_only
        )
        assert sov_in_table_only


class TestSectionDetection:
    """Test section detection functionality."""
    
    @pytest.fixture
    def service(self):
        return HybridChunkingService()
    
    @pytest.mark.parametrize("text,expected_section", [
        ("DECLARATIONS\nPolicy Number: 123", SectionType.DECLARATIONS),
        ("POLICY DECLARATIONS\nNamed Insured: ABC", SectionType.DECLARATIONS),
        ("COVERAGES\nCoverage A - Building", SectionType.COVERAGES),
        ("COVERAGE FORM\nProperty Coverage", SectionType.COVERAGES),
        ("CONDITIONS\nDuties in Event of Loss", SectionType.CONDITIONS),
        ("GENERAL CONDITIONS\nNotice requirements", SectionType.CONDITIONS),
        ("EXCLUSIONS\nWe do not cover", SectionType.EXCLUSIONS),
        ("ENDORSEMENTS\nEndorsement No. 1", SectionType.ENDORSEMENTS),
        ("SCHEDULE OF VALUES\nLocation 1", SectionType.SCHEDULE_OF_VALUES),
        ("SOV\nBuilding values", SectionType.SCHEDULE_OF_VALUES),
        ("LOSS RUN\nClaim history", SectionType.LOSS_RUN),
        ("LOSS HISTORY\nPrior claims", SectionType.LOSS_RUN),
        ("Random text without section header", SectionType.UNKNOWN),
    ])
    def test_section_type_detection(self, service, text, expected_section):
        """Test detection of various section types."""
        detected = service._detect_section_type(text)
        assert detected == expected_section


class TestChunkSplitting:
    """Test chunk splitting functionality."""
    
    @pytest.fixture
    def service(self):
        return HybridChunkingService(max_tokens=100, overlap_tokens=10)
    
    def test_large_page_split(self, service):
        """Test that large pages are split into multiple chunks."""
        # Create a large page that exceeds token limit
        large_text = "DECLARATIONS\n\n" + ("This is a long paragraph. " * 100)
        
        page = PageData(
            page_number=1,
            text=large_text,
            metadata={},
        )
        
        result = service.chunk_pages([page])
        
        # Should be split into multiple chunks
        assert len(result.chunks) > 1
        
        # All chunks should have same section type
        section_types = set(c.metadata.section_type for c in result.chunks)
        assert len(section_types) == 1
    
    def test_small_page_not_split(self, service):
        """Test that small pages are not split."""
        small_text = "DECLARATIONS\n\nPolicy Number: 123"
        
        page = PageData(
            page_number=1,
            text=small_text,
            metadata={},
        )
        
        result = service.chunk_pages([page])
        
        # Should be single chunk
        assert len(result.chunks) == 1

