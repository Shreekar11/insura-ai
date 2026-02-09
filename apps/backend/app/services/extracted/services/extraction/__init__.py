"""Extraction services for structured data extraction from documents.

This package is organized into submodules:
- section/: Section-level extraction and cross-section validation

Base classes:
- BaseExtractor: Abstract base class for all extractors
- ExtractorFactory: Factory for creating extractors dynamically

Two-document pipeline:
- BaseFormExtractor: Extracts standard provisions from ISO base forms
- DocumentTypeClassifier: Identifies base forms vs endorsements
"""

from app.services.extracted.services.extraction.base_extractor import BaseExtractor
from app.services.extracted.services.extraction.extractor_factory import ExtractorFactory
from app.services.enriched.services.entity.resolver import EntityResolver
from app.services.extracted.services.extraction.section import (
    SectionExtractionOrchestrator,
    SectionExtractionResult,
    DocumentExtractionResult,
)
from app.services.extracted.services.extraction.base_form_extractor import BaseFormExtractor
from app.services.extracted.services.document_type_classifier import DocumentTypeClassifier

__all__ = [
    # Base classes
    "BaseExtractor",
    "ExtractorFactory",
    "EntityResolver",
    # Section extraction
    "SectionExtractionOrchestrator",
    "SectionExtractionResult",
    "DocumentExtractionResult",
    # Two-document pipeline
    "BaseFormExtractor",
    "DocumentTypeClassifier",
]
