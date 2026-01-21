"""Verification tests for semantic chunking logic.

Tests:
- Endorsement splitting (Dual Emission) when semantic_role='both'
- Effective section type projection for coverage_modifier and exclusion_modifier
- Prioritization of SectionBoundary over page_section_map
"""

import pytest
from uuid import uuid4
from typing import List

from app.services.processed.services.chunking.hybrid_chunking_service import HybridChunkingService
from app.services.processed.services.chunking.hybrid_models import SectionType
from app.models.page_data import PageData
from app.models.page_analysis_models import SectionBoundary, SemanticRole, PageType

class TestSemanticChunkingVerification:
    
    @pytest.fixture
    def service(self):
        return HybridChunkingService()
    
    def test_endorsement_split_both(self, service):
        """Test that an endorsement with semantic_role='both' is split into two chunks."""
        page = PageData(
            page_number=1,
            text="This endorsement adds coverage for hired autos but excludes racing.",
            markdown="# Endorsement\n\nThis endorsement adds coverage for hired autos but excludes racing.",
            metadata={}
        )
        
        boundaries = [
            SectionBoundary(
                section_type=PageType.ENDORSEMENT,
                start_page=1,
                end_page=1,
                confidence=1.0,
                page_count=1,
                semantic_role=SemanticRole.BOTH,
                effective_section_type=PageType.ENDORSEMENT # 'Both' projects to endorsement (dual emitted in chunker)
            )
        ]
        
        result = service.chunk_pages([page], section_boundaries=boundaries)
        
        # Verify and assert
        assert len(result.chunks) == 2, "Should have created 2 chunks (one for coverages, one for exclusions)"
        
        section_types = [c.metadata.section_type for c in result.chunks]
        assert all(st == SectionType.ENDORSEMENTS for st in section_types)
        
        eff_types = [c.metadata.effective_section_type for c in result.chunks]
        assert SectionType.COVERAGES in eff_types
        assert SectionType.EXCLUSIONS in eff_types
        
        for chunk in result.chunks:
            assert chunk.metadata.semantic_role == SemanticRole.BOTH
            assert "projected_from_endorsements" in chunk.metadata.subsection_type

    def test_coverage_modifier_projection(self, service):
        """Test that an endorsement with coverage_modifier is projected to COVERAGES."""
        page = PageData(
            page_number=1,
            text="This endorsement adds coverage for hired autos.",
            markdown="# Endorsement\n\nThis endorsement adds coverage.",
            metadata={}
        )
        
        boundaries = [
            SectionBoundary(
                section_type=PageType.ENDORSEMENT,
                start_page=1,
                end_page=1,
                confidence=1.0,
                page_count=1,
                semantic_role=SemanticRole.COVERAGE_MODIFIER,
                effective_section_type=PageType.COVERAGES
            )
        ]
        
        result = service.chunk_pages([page], section_boundaries=boundaries)
        
        assert len(result.chunks) == 1
        assert result.chunks[0].metadata.section_type == SectionType.ENDORSEMENTS
        assert result.chunks[0].metadata.effective_section_type == SectionType.COVERAGES
        assert result.chunks[0].metadata.semantic_role == SemanticRole.COVERAGE_MODIFIER

    def test_exclusion_modifier_projection(self, service):
        """Test that an endorsement with exclusion_modifier is projected to EXCLUSIONS."""
        page = PageData(
            page_number=1,
            text="This endorsement excludes racing.",
            markdown="# Endorsement\n\nThis endorsement excludes racing.",
            metadata={}
        )
        
        boundaries = [
            SectionBoundary(
                section_type=PageType.ENDORSEMENT,
                start_page=1,
                end_page=1,
                confidence=1.0,
                page_count=1,
                semantic_role=SemanticRole.EXCLUSION_MODIFIER
            )
        ]
        
        result = service.chunk_pages([page], section_boundaries=boundaries)
        
        assert len(result.chunks) == 1
        assert result.chunks[0].metadata.section_type == SectionType.ENDORSEMENTS
        assert result.chunks[0].metadata.effective_section_type == SectionType.EXCLUSIONS
        assert result.chunks[0].metadata.semantic_role == SemanticRole.EXCLUSION_MODIFIER

    def test_boundary_priority_over_page_map(self, service):
        """Test that SectionBoundary takes precedence over page_section_map."""
        page = PageData(
            page_number=1,
            text="This page is classified as unknown in map but has a boundary.",
            markdown="Text content",
            metadata={}
        )
        
        # Page map says UNKNOWN
        page_map = {1: "unknown"}
        
        # Boundary says COVERAGES
        boundaries = [
            SectionBoundary(
                section_type=PageType.COVERAGES,
                start_page=1,
                end_page=1,
                confidence=1.0,
                page_count=1
            )
        ]
        
        result = service.chunk_pages([page], page_section_map=page_map, section_boundaries=boundaries)
        
        assert len(result.chunks) == 1
        assert result.chunks[0].metadata.section_type == SectionType.COVERAGES

if __name__ == "__main__":
    # This allows running it directly if needed
    pytest.main([__file__])
