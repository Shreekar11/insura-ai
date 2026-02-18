import pytest
from app.utils.section_type_mapper import SectionTypeMapper
from app.models.page_analysis_models import PageType, SemanticRole

class TestSectionTypeMapperEndorsement:
    """Test suite for SectionTypeMapper endorsement projection."""
    
    def test_resolve_both_role(self):
        """Test that BOTH role projects to COVERAGES."""
        # Using string value for test flexibility
        result = SectionTypeMapper.resolve_effective_section_type(
            PageType.ENDORSEMENT, 
            SemanticRole.BOTH
        )
        assert result == PageType.COVERAGES
        
    def test_resolve_coverage_role(self):
        """Test that COVERAGE_MODIFIER role projects to COVERAGES."""
        result = SectionTypeMapper.resolve_effective_section_type(
            PageType.ENDORSEMENT, 
            SemanticRole.COVERAGE_MODIFIER
        )
        assert result == PageType.COVERAGES
        
    def test_resolve_exclusion_role(self):
        """Test that EXCLUSION_MODIFIER role projects to EXCLUSIONS."""
        result = SectionTypeMapper.resolve_effective_section_type(
            PageType.ENDORSEMENT, 
            SemanticRole.EXCLUSION_MODIFIER
        )
        assert result == PageType.EXCLUSIONS
        
    def test_resolve_base_policy_unaffected(self):
        """Test that base policy sections are authoritative and exit early."""
        # COVERAGES should return as-is regardless of semantic_role (which shouldn't exist for base)
        result = SectionTypeMapper.resolve_effective_section_type(
            PageType.COVERAGES, 
            "some_role"
        )
        assert result == PageType.COVERAGES
        
    def test_resolve_certificate_hard_guard(self):
        """Test that CERTIFICATE_OF_INSURANCE is never projected."""
        result = SectionTypeMapper.resolve_effective_section_type(
            PageType.CERTIFICATE_OF_INSURANCE, 
            SemanticRole.COVERAGE_MODIFIER
        )
        assert result == PageType.CERTIFICATE_OF_INSURANCE
