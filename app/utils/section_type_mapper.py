"""Canonical section type mapper service.

This service provides a single source of truth for mapping between PageType
and SemanticSection enums, ensuring consistent taxonomy across the pipeline.
"""

from typing import Optional
from app.models.page_analysis_models import PageType, SemanticSection
from app.services.processed.services.chunking.hybrid_models import SectionType
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class SectionTypeMapper:
    """Maps PageType values to canonical SectionType values and SemanticSections.
    
    This mapper ensures consistent section taxonomy across the pipeline by
    providing a single source of truth for section type conversions.
    """
    
    # Mapping from PageType to high-level SemanticSection (NEW)
    PAGE_TO_SEMANTIC_MAP: dict[PageType, SemanticSection] = {
        PageType.DECLARATIONS: SemanticSection.DECLARATIONS,
        PageType.COVERAGES: SemanticSection.COVERAGES,
        PageType.CONDITIONS: SemanticSection.CONDITIONS,
        PageType.EXCLUSIONS: SemanticSection.EXCLUSIONS,
        PageType.ENDORSEMENT: SemanticSection.ENDORSEMENT,
        PageType.SOV: SemanticSection.SOV,
        PageType.LOSS_RUN: SemanticSection.LOSS_RUN,
        PageType.DEFINITIONS: SemanticSection.DEFINITIONS,
        PageType.BOILERPLATE: SemanticSection.BOILERPLATE,
        PageType.CERTIFICATE_OF_INSURANCE: SemanticSection.CERTIFICATE_OF_INSURANCE,
        PageType.LIABILITY_COVERAGES: SemanticSection.LIABILITY_COVERAGE,
        PageType.COVERAGE_GRANT: SemanticSection.COVERAGES,
        PageType.COVERAGE_EXTENSION: SemanticSection.COVERAGES,
        PageType.LIMITS: SemanticSection.COVERAGES,
        PageType.INSURED_DEFINITION: SemanticSection.COVERAGES,
        PageType.VEHICLE_DETAILS: SemanticSection.DECLARATIONS,
        PageType.INSURED_DECLARED_VALUE: SemanticSection.DECLARATIONS,
        PageType.UNKNOWN: SemanticSection.UNKNOWN,
    }
    # Canonical mapping from PageType to SectionType (Legacy/Chunking)
    PAGE_TO_SECTION_MAP: dict[PageType, SectionType] = {
        PageType.DECLARATIONS: SectionType.DECLARATIONS,
        PageType.COVERAGES: SectionType.COVERAGES,
        PageType.CONDITIONS: SectionType.CONDITIONS,
        PageType.EXCLUSIONS: SectionType.EXCLUSIONS,
        PageType.ENDORSEMENT: SectionType.ENDORSEMENTS,
        PageType.SOV: SectionType.SOV,
        PageType.LOSS_RUN: SectionType.LOSS_RUN,
        PageType.DEFINITIONS: SectionType.DEFINITIONS,
        PageType.INVOICE: SectionType.UNKNOWN,
        PageType.BOILERPLATE: SectionType.UNKNOWN,
        PageType.DUPLICATE: SectionType.UNKNOWN,
        PageType.TABLE_OF_CONTENTS: SectionType.UNKNOWN,
        PageType.VEHICLE_DETAILS: SectionType.VEHICLE_DETAILS,
        PageType.INSURED_DECLARED_VALUE: SectionType.INSURED_DECLARED_VALUE,
        PageType.LIABILITY_COVERAGES: SectionType.LIABILITY_COVERAGES,
        PageType.DEDUCTIBLES: SectionType.DEDUCTIBLES,
        PageType.PREMIUM: SectionType.PREMIUM,
        PageType.COVERAGES_CONTEXT: SectionType.COVERAGES_CONTEXT,
        PageType.COVERAGE_GRANT: SectionType.COVERAGE_GRANT,
        PageType.COVERAGE_EXTENSION: SectionType.COVERAGE_EXTENSION,
        PageType.LIMITS: SectionType.LIMITS,
        PageType.INSURED_DEFINITION: SectionType.INSURED_DEFINITION,
        PageType.CERTIFICATE_OF_INSURANCE: SectionType.CERTIFICATE_OF_INSURANCE,
        PageType.UNKNOWN: SectionType.UNKNOWN,
    }
    
    GRANULAR_TO_CORE_MAP: dict[SectionType, SectionType] = {
        SectionType.VEHICLE_DETAILS: SectionType.COVERAGES,
        SectionType.INSURED_DECLARED_VALUE: SectionType.COVERAGES,
        SectionType.LIABILITY_COVERAGES: SectionType.COVERAGES,
        SectionType.INSURING_AGREEMENT: SectionType.COVERAGES,
        SectionType.PREMIUM_SUMMARY: SectionType.DECLARATIONS,
        SectionType.FINANCIAL_STATEMENT: SectionType.DECLARATIONS,
    }

    
    # Reverse mapping for SectionType -> PageType
    SECTION_TO_PAGE_MAP: dict[SectionType, PageType] = {
        SectionType.DECLARATIONS: PageType.DECLARATIONS,
        SectionType.COVERAGES: PageType.COVERAGES,
        SectionType.CONDITIONS: PageType.CONDITIONS,
        SectionType.EXCLUSIONS: PageType.EXCLUSIONS,
        SectionType.ENDORSEMENTS: PageType.ENDORSEMENT,
        SectionType.SOV: PageType.SOV,
        SectionType.LOSS_RUN: PageType.LOSS_RUN,
        SectionType.DEFINITIONS: PageType.DEFINITIONS,
        SectionType.INSURING_AGREEMENT: PageType.UNKNOWN,
        SectionType.PREMIUM_SUMMARY: PageType.UNKNOWN,
        SectionType.FINANCIAL_STATEMENT: PageType.UNKNOWN,
        SectionType.VEHICLE_DETAILS: PageType.VEHICLE_DETAILS,
        SectionType.INSURED_DECLARED_VALUE: PageType.INSURED_DECLARED_VALUE,
        SectionType.LIABILITY_COVERAGES: PageType.LIABILITY_COVERAGES,
        SectionType.DEDUCTIBLES: PageType.DEDUCTIBLES,
        SectionType.PREMIUM: PageType.PREMIUM,
        SectionType.COVERAGES_CONTEXT: PageType.COVERAGES_CONTEXT,
        SectionType.UNKNOWN: PageType.UNKNOWN,
    }
    
    # String-based mapping for flexible conversion
    STRING_TO_SECTION_MAP: dict[str, SectionType] = {
        "declarations": SectionType.DECLARATIONS,
        "coverages": SectionType.COVERAGES,
        "conditions": SectionType.CONDITIONS,
        "exclusions": SectionType.EXCLUSIONS,
        "endorsement": SectionType.ENDORSEMENTS,
        "endorsements": SectionType.ENDORSEMENTS,
        "sov": SectionType.SOV,
        "schedule_of_values": SectionType.SOV,
        "statement_of_values": SectionType.SOV,
        "loss_run": SectionType.LOSS_RUN,
        "definitions": SectionType.DEFINITIONS,
        "insuring_agreement": SectionType.INSURING_AGREEMENT,
        "premium_summary": SectionType.PREMIUM_SUMMARY,
        "financial_statement": SectionType.FINANCIAL_STATEMENT,
        "vehicle_details": SectionType.VEHICLE_DETAILS,
        "insured_declared_value": SectionType.INSURED_DECLARED_VALUE,
        "liability_coverages": SectionType.LIABILITY_COVERAGES,
        "deductibles": SectionType.DEDUCTIBLES,
        "premium": SectionType.PREMIUM,
        "coverages_context": SectionType.COVERAGES_CONTEXT,
        "coverage_grant": SectionType.COVERAGE_GRANT,
        "coverage_extension": SectionType.COVERAGE_EXTENSION,
        "limits": SectionType.LIMITS,
        "insured_definition": SectionType.INSURED_DEFINITION,
        "certificate_of_insurance": SectionType.CERTIFICATE_OF_INSURANCE,
        "acord_certificate": SectionType.CERTIFICATE_OF_INSURANCE,
        "unknown": SectionType.UNKNOWN,
    }
    
    @classmethod
    def page_to_semantic(cls, page_type: PageType) -> SemanticSection:
        """Map PageType to SemanticSection."""
        return cls.PAGE_TO_SEMANTIC_MAP.get(page_type, SemanticSection.UNKNOWN)
    @classmethod
    def page_type_to_section_type(cls, page_type: PageType) -> SectionType:
        """Convert PageType to canonical SectionType.
        
        Args:
            page_type: PageType enum value
            
        Returns:
            Canonical SectionType enum value
        """
        return cls.PAGE_TO_SECTION_MAP.get(page_type, SectionType.UNKNOWN)

    @classmethod
    def section_type_to_page_type(cls, section_type: SectionType) -> PageType:
        """Convert SectionType to canonical PageType.
        
        Args:
            section_type: SectionType enum value
            
        Returns:
            Canonical PageType enum value
        """
        return cls.SECTION_TO_PAGE_MAP.get(section_type, PageType.UNKNOWN)
    
    @classmethod
    def string_to_section_type(cls, section_str: str) -> SectionType:
        """Convert string to canonical SectionType.
        
        Handles both PageType string values and SectionType string values,
        normalizing them to canonical SectionType.
        
        Args:
            section_str: Section type as string
            
        Returns:
            Canonical SectionType enum value
        """
        normalized = section_str.lower().strip()
        return cls.STRING_TO_SECTION_MAP.get(normalized, SectionType.UNKNOWN)
    
    @classmethod
    def normalize_page_section_map(
        cls,
        page_section_map: dict[int, str]
    ) -> dict[int, SectionType]:
        """Normalize page_section_map to use canonical SectionType values.
        
        Args:
            page_section_map: Mapping of page numbers to section type strings
            
        Returns:
            Dict mapping page numbers to canonical SectionType enums
        """
        normalized_map = {}
        for page_num, section_str in page_section_map.items():
            section_type = cls.string_to_section_type(section_str)
            normalized_map[page_num] = section_type
            
            # Log if normalization changed the value
            if section_str.lower() != section_type.value:
                LOGGER.debug(
                    f"Normalized section type for page {page_num}: '{section_str}' -> '{section_type.value}'"
                )
        
        return normalized_map
    
    @classmethod
    def normalize_section_boundary(
        cls,
        page_type: PageType
    ) -> SemanticSection:
        """Normalize a PageType from section boundary to SemanticSection.
        
        Args:
            page_type: PageType from section boundary
            
        Returns:
            Canonical SemanticSection
        """
        return cls.page_to_semantic(page_type)

    @classmethod
    def normalize_to_core_section(cls, section_type: SectionType) -> SectionType:
        """Normalize a granular section type to a core policy section type.
        
        Maps motor-policy-specific section types to core policy sections 
        that have extractors (e.g., vehicle_details -> declarations).
        
        Args:
            section_type: The granular SectionType to normalize
            
        Returns:
            Core SectionType for chunking/extraction
        """
        return cls.GRANULAR_TO_CORE_MAP.get(section_type, section_type)
    
    @classmethod
    def normalize_string_to_core_section(cls, section_str: str) -> SectionType:
        """Normalize a section string to a core policy section type.
        
        Args:
            section_str: Section type as string
            
        Returns:
            Core SectionType for chunking/extraction
        """
        section_type = cls.string_to_section_type(section_str)
        return cls.normalize_to_core_section(section_type)
    # Mapping from granular SectionType to core product concepts
    # This is used for checking if a document "has coverages", etc.
    PRODUCT_CONCEPT_MAP: dict[SectionType, str] = {
        SectionType.DECLARATIONS: "declarations",
        SectionType.VEHICLE_DETAILS: "declarations",
        SectionType.INSURED_DECLARED_VALUE: "declarations",
        SectionType.PREMIUM_SUMMARY: "declarations",
        SectionType.FINANCIAL_STATEMENT: "declarations",
        SectionType.COVERAGES: "coverages",
        SectionType.LIABILITY_COVERAGES: "coverages",
        SectionType.INSURING_AGREEMENT: "coverages",
        SectionType.CONDITIONS: "conditions",
        SectionType.EXCLUSIONS: "exclusions",
        SectionType.ENDORSEMENTS: "endorsements",
        SectionType.DEFINITIONS: "definitions",
        SectionType.SOV: "sov",
        SectionType.LOSS_RUN: "loss_run",
        SectionType.DEDUCTIBLES: "deductibles",
        SectionType.PREMIUM: "premium",
        SectionType.COVERAGES_CONTEXT: "coverages",
    }

    @classmethod
    def get_product_concepts(cls, section_types: list[SectionType]) -> list[str]:
        """Map a list of SectionTypes to unique core product concepts.
        
        Args:
            section_types: List of SectionType enums
            
        Returns:
            List of unique product concept strings
        """
        concepts = set()
        for st in section_types:
            concept = cls.PRODUCT_CONCEPT_MAP.get(st)
            if concept:
                concepts.add(concept)
        return sorted(list(concepts))

    @classmethod
    def resolve_effective_section_type(
        cls, 
        page_type: PageType, 
        semantic_role: Optional[str]
    ) -> PageType:
        """Resolve a physical page type to its effective extraction type.
        
        Implements semantic projection for endorsements and validates 
        core policy sections.
        """
        # 1. Base Policy Sections are authoritative
        authoritative = {
            PageType.COVERAGES, 
            PageType.EXCLUSIONS, 
            PageType.CONDITIONS, 
            PageType.DEFINITIONS,
            PageType.DECLARATIONS
        }
        if page_type in authoritative or page_type in {
            PageType.COVERAGE_GRANT, 
            PageType.COVERAGE_EXTENSION, 
            PageType.LIMITS, 
            PageType.INSURED_DEFINITION
        }:
            return page_type
            
        # 2. Endorsement Semantic Projection
        if page_type == PageType.ENDORSEMENT and semantic_role:
            # HARD GUARD: Certificate of insurance should NEVER be projected
            # This handles cases where a certificate page is misclassified or mis-analyzed
            if page_type == PageType.CERTIFICATE_OF_INSURANCE:
                return PageType.CERTIFICATE_OF_INSURANCE

            from app.models.page_analysis_models import SemanticRole
            
            # String comparison to be enum-safe
            role_val = semantic_role.value if hasattr(semantic_role, 'value') else str(semantic_role)
            
            if role_val == SemanticRole.COVERAGE_MODIFIER:
                return PageType.COVERAGES
            elif role_val == SemanticRole.EXCLUSION_MODIFIER:
                return PageType.EXCLUSIONS
                
        # 3. Default: Use original page type
        return page_type
