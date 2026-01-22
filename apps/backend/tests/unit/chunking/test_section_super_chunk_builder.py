"""Unit tests for SectionSuperChunkBuilder.

Tests the super-chunk building functionality including:
- Building super-chunks from hybrid chunks
- Creating processing batches
- Merging small super-chunks
- Extraction order determination
"""

import pytest
from uuid import uuid4

from app.services.processed.services.chunking.section_super_chunk_builder import (
    SectionSuperChunkBuilder,
    SuperChunkBatch,
)
from app.services.processed.services.chunking.hybrid_models import (
    SectionType,
    ChunkRole,
    HybridChunk,
    HybridChunkMetadata,
    SectionSuperChunk,
    SECTION_CONFIG,
)


class TestSectionSuperChunkBuilder:
    """Test suite for SectionSuperChunkBuilder."""
    
    @pytest.fixture
    def builder(self):
        """Create builder instance."""
        return SectionSuperChunkBuilder(
            max_tokens_per_super_chunk=8000,
            max_tokens_per_batch=12000,
        )
    
    @pytest.fixture
    def sample_chunks(self):
        """Create sample hybrid chunks for testing."""
        document_id = uuid4()
        
        chunks = []
        
        # Declarations chunks
        for i in range(2):
            chunks.append(HybridChunk(
                text=f"Declarations content {i}",
                metadata=HybridChunkMetadata(
                    document_id=document_id,
                    page_number=i + 1,
                    section_type=SectionType.DECLARATIONS,
                    chunk_index=i,
                    token_count=500,
                ),
            ))
        
        # Coverages chunks
        for i in range(4):
            chunks.append(HybridChunk(
                text=f"Coverage content {i}",
                metadata=HybridChunkMetadata(
                    document_id=document_id,
                    page_number=i + 3,
                    section_type=SectionType.COVERAGES,
                    chunk_index=i,
                    token_count=800,
                ),
            ))
        
        # Conditions chunk
        chunks.append(HybridChunk(
            text="Conditions content",
            metadata=HybridChunkMetadata(
                document_id=document_id,
                page_number=7,
                section_type=SectionType.CONDITIONS,
                chunk_index=0,
                token_count=600,
            ),
        ))
        
        # SOV chunk (table-only)
        chunks.append(HybridChunk(
            text="SOV table content",
            metadata=HybridChunkMetadata(
                document_id=document_id,
                page_number=8,
                section_type=SectionType.SOV,
                chunk_index=0,
                token_count=1000,
            ),
        ))
        
        return chunks
    
    def test_init(self, builder):
        """Test builder initialization."""
        assert builder.max_tokens_per_super_chunk == 8000
        assert builder.max_tokens_per_batch == 12000
    
    def test_build_super_chunks_empty(self, builder):
        """Test building with empty chunks list."""
        result = builder.build_super_chunks([])
        assert result == []
    
    def test_build_super_chunks_groups_by_section(self, builder, sample_chunks):
        """Test that chunks are grouped by section type."""
        super_chunks = builder.build_super_chunks(sample_chunks)
        
        # Should have super-chunks for each section type
        section_types = {sc.section_type for sc in super_chunks}
        
        assert SectionType.DECLARATIONS in section_types
        assert SectionType.COVERAGES in section_types
        assert SectionType.CONDITIONS in section_types
        assert SectionType.SOV in section_types
    
    def test_build_super_chunks_correct_chunk_count(self, builder, sample_chunks):
        """Test that super-chunks contain correct number of chunks."""
        super_chunks = builder.build_super_chunks(sample_chunks)
        
        # Find declarations super-chunks (may be split due to max_chunks=1 in config)
        decl_scs = [
            sc for sc in super_chunks 
            if sc.section_type == SectionType.DECLARATIONS
        ]
        total_decl_chunks = sum(len(sc.chunks) for sc in decl_scs)
        assert total_decl_chunks == 2
        
        # Find coverages super-chunk
        cov_sc = next(
            sc for sc in super_chunks 
            if sc.section_type == SectionType.COVERAGES
        )
        assert len(cov_sc.chunks) == 4
    
    def test_build_super_chunks_sorted_by_priority(self, builder, sample_chunks):
        """Test that super-chunks are sorted by priority."""
        super_chunks = builder.build_super_chunks(sample_chunks)
        
        priorities = [sc.processing_priority for sc in super_chunks]
        assert priorities == sorted(priorities)
    
    def test_build_super_chunks_with_document_id(self, builder, sample_chunks):
        """Test that document_id is set on super-chunks."""
        document_id = uuid4()
        super_chunks = builder.build_super_chunks(sample_chunks, document_id)
        
        for sc in super_chunks:
            assert sc.document_id == document_id
            assert sc.super_chunk_id is not None
            assert str(document_id) in sc.super_chunk_id
    
    def test_super_chunk_tokens_calculated(self, builder, sample_chunks):
        """Test that total tokens are calculated correctly."""
        super_chunks = builder.build_super_chunks(sample_chunks)
        
        for sc in super_chunks:
            expected_tokens = sum(c.metadata.token_count for c in sc.chunks)
            assert sc.total_tokens == expected_tokens
    
    def test_super_chunk_requires_llm_flag(self, builder, sample_chunks):
        """Test that requires_llm flag is set correctly."""
        super_chunks = builder.build_super_chunks(sample_chunks)
        
        for sc in super_chunks:
            config = SECTION_CONFIG.get(sc.section_type, {})
            assert sc.requires_llm == config.get("requires_llm", True)
    
    def test_super_chunk_table_only_flag(self, builder, sample_chunks):
        """Test that table_only flag is set correctly."""
        super_chunks = builder.build_super_chunks(sample_chunks)
        
        # SOV should be table_only
        sov_sc = next(
            sc for sc in super_chunks 
            if sc.section_type == SectionType.SOV
        )
        assert sov_sc.table_only is True
        
        # Declarations should not be table_only
        decl_sc = next(
            sc for sc in super_chunks 
            if sc.section_type == SectionType.DECLARATIONS
        )
        assert decl_sc.table_only is False


class TestProcessingBatches:
    """Test batch creation functionality."""
    
    @pytest.fixture
    def builder(self):
        return SectionSuperChunkBuilder(
            max_tokens_per_super_chunk=8000,
            max_tokens_per_batch=5000,  # Small for testing
        )
    
    @pytest.fixture
    def super_chunks(self):
        """Create sample super-chunks."""
        return [
            SectionSuperChunk(
                section_type=SectionType.DECLARATIONS,
                section_name="Declarations",
                total_tokens=2000,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.COVERAGES,
                section_name="Coverages",
                total_tokens=3000,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.CONDITIONS,
                section_name="Conditions",
                total_tokens=1500,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.SOV,
                section_name="SOV",
                total_tokens=2000,
                requires_llm=False,
                table_only=True,
            ),
        ]
    
    def test_create_batches_empty(self, builder):
        """Test batch creation with empty list."""
        batches = builder.create_processing_batches([])
        assert batches == []
    
    def test_create_batches_filters_non_llm(self, builder, super_chunks):
        """Test that non-LLM sections are filtered."""
        batches = builder.create_processing_batches(super_chunks)
        
        # SOV should not be in any batch
        for batch in batches:
            for sc in batch.super_chunks:
                assert sc.section_type != SectionType.SOV
    
    def test_create_batches_respects_token_limit(self, builder, super_chunks):
        """Test that batches respect token limit."""
        batches = builder.create_processing_batches(super_chunks)
        
        for batch in batches:
            # Each batch should be under limit (or have single super-chunk)
            if len(batch.super_chunks) > 1:
                assert batch.total_tokens <= builder.max_tokens_per_batch
    
    def test_batch_has_correct_metadata(self, builder, super_chunks):
        """Test that batch metadata is correct."""
        batches = builder.create_processing_batches(super_chunks)
        
        for i, batch in enumerate(batches):
            assert batch.batch_index == i
            assert batch.total_tokens == sum(
                sc.total_tokens for sc in batch.super_chunks
            )
            assert len(batch.section_types) == len(set(
                sc.section_type.value for sc in batch.super_chunks
            ))


class TestMergeSmallSuperChunks:
    """Test merging of small super-chunks."""
    
    @pytest.fixture
    def builder(self):
        return SectionSuperChunkBuilder()
    
    def test_merge_small_chunks(self, builder):
        """Test that small super-chunks are merged."""
        # Create super-chunks with actual chunks so merge can work
        from app.services.processed.services.chunking.hybrid_models import HybridChunk, HybridChunkMetadata
        
        chunk1 = HybridChunk(
            text="Condition content 1",
            metadata=HybridChunkMetadata(
                section_type=SectionType.CONDITIONS,
                token_count=200,
            ),
        )
        chunk2 = HybridChunk(
            text="Condition content 2",
            metadata=HybridChunkMetadata(
                section_type=SectionType.CONDITIONS,
                token_count=200,
            ),
        )
        
        super_chunks = [
            SectionSuperChunk(
                section_type=SectionType.CONDITIONS,
                section_name="Conditions 1",
                chunks=[chunk1],
                total_tokens=200,
            ),
            SectionSuperChunk(
                section_type=SectionType.CONDITIONS,
                section_name="Conditions 2",
                chunks=[chunk2],
                total_tokens=200,
            ),
        ]
        
        merged = builder.merge_small_super_chunks(super_chunks, min_tokens=500)
        
        # Should be merged into one
        assert len(merged) == 1
        assert merged[0].section_type == SectionType.CONDITIONS
    
    def test_large_chunks_not_merged(self, builder):
        """Test that large super-chunks are not merged."""
        super_chunks = [
            SectionSuperChunk(
                section_type=SectionType.COVERAGES,
                section_name="Coverages",
                total_tokens=2000,
            ),
            SectionSuperChunk(
                section_type=SectionType.CONDITIONS,
                section_name="Conditions",
                total_tokens=1500,
            ),
        ]
        
        merged = builder.merge_small_super_chunks(super_chunks, min_tokens=500)
        
        # Should remain separate (different section types)
        assert len(merged) == 2


class TestExtractionOrder:
    """Test extraction order determination."""
    
    @pytest.fixture
    def builder(self):
        return SectionSuperChunkBuilder()
    
    def test_extraction_order_llm_first(self, builder):
        """Test that LLM sections come before table-only."""
        super_chunks = [
            SectionSuperChunk(
                section_type=SectionType.SOV,
                section_name="SOV",
                requires_llm=False,
                table_only=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.DECLARATIONS,
                section_name="Declarations",
                requires_llm=True,
            ),
        ]
        
        ordered = builder.get_extraction_order(super_chunks)
        
        # LLM sections should come first
        assert ordered[0].requires_llm is True
        assert ordered[-1].table_only is True
    
    def test_extraction_order_by_priority(self, builder):
        """Test that LLM sections are ordered by priority."""
        super_chunks = [
            SectionSuperChunk(
                section_type=SectionType.CONDITIONS,
                section_name="Conditions",
                processing_priority=3,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.DECLARATIONS,
                section_name="Declarations",
                processing_priority=1,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.COVERAGES,
                section_name="Coverages",
                processing_priority=2,
                requires_llm=True,
            ),
        ]
        
        ordered = builder.get_extraction_order(super_chunks)
        
        priorities = [sc.processing_priority for sc in ordered]
        assert priorities == sorted(priorities)


class TestLLMCallEstimation:
    """Test LLM call estimation."""
    
    @pytest.fixture
    def builder(self):
        return SectionSuperChunkBuilder(max_tokens_per_batch=5000)
    
    def test_estimate_llm_calls(self, builder):
        """Test LLM call estimation."""
        super_chunks = [
            SectionSuperChunk(
                section_type=SectionType.DECLARATIONS,
                section_name="Declarations",
                total_tokens=2000,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.COVERAGES,
                section_name="Coverages",
                total_tokens=3000,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.SOV,
                section_name="SOV",
                total_tokens=1000,
                requires_llm=False,
                table_only=True,
            ),
        ]
        
        estimate = builder.estimate_llm_calls(super_chunks)
        
        assert estimate["tier1_calls"] == 1
        assert estimate["tier3_calls"] == 1
        assert estimate["tier2_calls"] >= 1
        assert estimate["table_only_sections"] == 1
        assert estimate["total_llm_tokens"] == 5000  # Only LLM-required

