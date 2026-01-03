"""Canonical section type mapper service.

This service provides a single source of truth for mapping between PageType
and SectionType enums, ensuring consistent taxonomy across the pipeline.
"""

from typing import Optional
from app.models.page_analysis_models import PageType
from app.services.processed.services.chunking.hybrid_models import SectionType
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class SectionTypeMapper:
    """Maps PageType values to canonical SectionType values.
    
    This mapper ensures consistent section taxonomy across the pipeline by
    providing a single source of truth for section type conversions.
    """
    
    # Canonical mapping from PageType to SectionType
    PAGE_TO_SECTION_MAP: dict[PageType, SectionType] = {
        PageType.DECLARATIONS: SectionType.DECLARATIONS,
        PageType.COVERAGES: SectionType.COVERAGES,
        PageType.CONDITIONS: SectionType.CONDITIONS,
        PageType.EXCLUSIONS: SectionType.EXCLUSIONS,
        PageType.ENDORSEMENT: SectionType.ENDORSEMENTS,
        PageType.SOV: SectionType.SCHEDULE_OF_VALUES,
        PageType.LOSS_RUN: SectionType.LOSS_RUN,
        PageType.DEFINITIONS: SectionType.DEFINITIONS,
        PageType.INVOICE: SectionType.UNKNOWN,
        PageType.BOILERPLATE: SectionType.UNKNOWN,
        PageType.DUPLICATE: SectionType.UNKNOWN,
        PageType.TABLE_OF_CONTENTS: SectionType.UNKNOWN,
        PageType.UNKNOWN: SectionType.UNKNOWN,
    }
    
    # Reverse mapping for SectionType -> PageType
    SECTION_TO_PAGE_MAP: dict[SectionType, PageType] = {
        SectionType.DECLARATIONS: PageType.DECLARATIONS,
        SectionType.COVERAGES: PageType.COVERAGES,
        SectionType.CONDITIONS: PageType.CONDITIONS,
        SectionType.EXCLUSIONS: PageType.EXCLUSIONS,
        SectionType.ENDORSEMENTS: PageType.ENDORSEMENT,
        SectionType.SCHEDULE_OF_VALUES: PageType.SOV,
        SectionType.LOSS_RUN: PageType.LOSS_RUN,
        SectionType.DEFINITIONS: PageType.DEFINITIONS,
        SectionType.INSURING_AGREEMENT: PageType.UNKNOWN,
        SectionType.PREMIUM_SUMMARY: PageType.UNKNOWN,
        SectionType.FINANCIAL_STATEMENT: PageType.UNKNOWN,
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
        "sov": SectionType.SCHEDULE_OF_VALUES,
        "schedule_of_values": SectionType.SCHEDULE_OF_VALUES,
        "loss_run": SectionType.LOSS_RUN,
        "definitions": SectionType.DEFINITIONS,
        "insuring_agreement": SectionType.INSURING_AGREEMENT,
        "premium_summary": SectionType.PREMIUM_SUMMARY,
        "financial_statement": SectionType.FINANCIAL_STATEMENT,
        "unknown": SectionType.UNKNOWN,
    }
    
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
    ) -> SectionType:
        """Normalize a PageType from section boundary to SectionType.
        
        Args:
            page_type: PageType from section boundary
            
        Returns:
            Canonical SectionType
        """
        return cls.page_type_to_section_type(page_type)

