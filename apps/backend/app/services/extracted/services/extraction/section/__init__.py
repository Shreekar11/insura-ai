"""Section extraction services for section-level data extraction.

This module contains services for:
- Section extraction orchestration (using factory pattern)
- Section-specific extractors
- Cross-section validation and reconciliation
- Two-document pipeline endorsement provision extraction
"""

from app.services.extracted.services.extraction.section.section_extraction_orchestrator import (
    SectionExtractionOrchestrator,
    SectionExtractionResult,
    DocumentExtractionResult,
)
from app.services.extracted.services.extraction.section.extractors import (
    DeclarationsExtractor,
    CoveragesExtractor,
    ConditionsExtractor,
    ExclusionsExtractor,
    EndorsementsExtractor,
    InsuringAgreementExtractor,
    PremiumSummaryExtractor,
    DefaultSectionExtractor,
    EndorsementCoverageProjectionExtractor,
    EndorsementExclusionProjectionExtractor,
)
from app.services.extracted.services.extraction.section.endorsement_provision_extractor import (
    EndorsementProvisionExtractor,
    EndorsementProvision,
    EndorsementProvisionResult,
)

__all__ = [
    # Orchestration
    "SectionExtractionOrchestrator",
    "SectionExtractionResult",
    "DocumentExtractionResult",
    # Section extractors
    "DeclarationsExtractor",
    "CoveragesExtractor",
    "ConditionsExtractor",
    "ExclusionsExtractor",
    "EndorsementsExtractor",
    "InsuringAgreementExtractor",
    "PremiumSummaryExtractor",
    "DefaultSectionExtractor",
    # Endorsement projection extractors
    "EndorsementCoverageProjectionExtractor",
    "EndorsementExclusionProjectionExtractor",
    # Two-document pipeline
    "EndorsementProvisionExtractor",
    "EndorsementProvision",
    "EndorsementProvisionResult",
]

