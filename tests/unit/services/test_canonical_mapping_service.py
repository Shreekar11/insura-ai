import pytest
from app.services.product.proposal_generation.canonical_mapping_service import CanonicalMappingService

class TestCanonicalMappingService:
    
    def test_coverage_mapping(self):
        # Known mappings
        assert CanonicalMappingService.get_canonical_name("coverages", "gl") == "General Liability"
        assert CanonicalMappingService.get_canonical_name("coverages", "comm auto") == "Commercial Auto"
        # Partial match
        assert CanonicalMappingService.get_canonical_name("coverages", "excess liability coverage") == "Excess Liability"
        # Fallback
        assert CanonicalMappingService.get_canonical_name("coverages", "random coverage") == "Random Coverage"

    def test_deductible_mapping(self):
        # Known mappings
        assert CanonicalMappingService.get_canonical_name("deductibles", "aop") == "All Other Perils"
        assert CanonicalMappingService.get_canonical_name("deductibles", "wind/hail") == "Wind/Hail"
        # Partial match
        assert CanonicalMappingService.get_canonical_name("deductibles", "wind storm") == "Wind/Hail"
        # Fallback
        assert CanonicalMappingService.get_canonical_name("deductibles", "special ded") == "Special Ded"

    def test_exclusion_mapping(self):
        # Currently just title casing
        assert CanonicalMappingService.get_canonical_name("exclusions", "war exclusion") == "War Exclusion"
        assert CanonicalMappingService.get_canonical_name("exclusions", "nuclear hazard") == "Nuclear Hazard"
        assert CanonicalMappingService.get_canonical_name("exclusions", "") == "Unknown Exclusion"

    def test_endorsement_mapping(self):
        # Currently just title casing
        assert CanonicalMappingService.get_canonical_name("endorsements", "additional insured") == "Additional Insured"
        assert CanonicalMappingService.get_canonical_name("endorsements", "waiver of subrogation") == "Waiver Of Subrogation"

    def test_unknown_section(self):
        assert CanonicalMappingService.get_canonical_name("unknown_section", "some field") == "Some Field"
        assert CanonicalMappingService.get_canonical_name("unknown_section", "") == "Unknown"
