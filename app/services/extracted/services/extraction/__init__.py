"""Extraction services for structured data extraction from documents.

This package is organized into submodules:
- table/: Table extraction, classification, normalization, and validation
- section/: Section-level extraction and cross-section validation
- document/: Document classification and section boundary detection

Base classes:
- BaseExtractor: Abstract base class for all extractors
- ExtractorFactory: Factory for creating extractors dynamically
"""

from app.services.extracted.services.extraction.base_extractor import BaseExtractor
from app.services.extracted.services.extraction.extractor_factory import ExtractorFactory
from app.services.enriched.services.entity.relationship_extractor import EntityRelationshipExtractor
from app.services.enriched.services.entity.resolver import EntityResolver

from app.services.extracted.services.extraction.document import (
    DocumentClassificationService,
    DocumentClassificationResult,
    SectionBoundary,
)
from app.services.extracted.services.extraction.section import (
    SectionExtractionOrchestrator,
    SectionExtractionResult,
    DocumentExtractionResult,
    CrossSectionValidator,
    CrossSectionValidationResult,
    ValidationIssue as CrossSectionValidationIssue,
    ReconciledValue,
)
from app.services.extracted.services.extraction.table import (
    TableExtractionService,
    TableStructure,
    TableCell,
    ColumnMapping,
    TableClassification,
    HeaderCanonicalizationService,
    RowNormalizationService,
    TableClassificationService,
    TableValidationService,
    ValidationIssue as TableValidationIssue,
    ValidationResult,
)

__all__ = [
    "BaseExtractor",
    "ExtractorFactory",
    "EntityRelationshipExtractor",
    "EntityResolver",
    "DocumentClassificationService",
    "DocumentClassificationResult",
    "SectionBoundary",
    "SectionExtractionOrchestrator",
    "SectionExtractionResult",
    "DocumentExtractionResult",
    "CrossSectionValidator",
    "CrossSectionValidationResult",
    "CrossSectionValidationIssue",
    "ReconciledValue",
    "TableExtractionService",
    "TableStructure",
    "TableCell",
    "ColumnMapping",
    "TableClassification",
    "HeaderCanonicalizationService",
    "RowNormalizationService",
    "TableClassificationService",
    "TableValidationService",
    "TableValidationIssue",
    "ValidationResult",
]
