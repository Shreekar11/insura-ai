"""Extraction services for structured data extraction from documents.

This package is organized into submodules:
- section/: Section-level extraction and cross-section validation

Base classes:
- BaseExtractor: Abstract base class for all extractors
- ExtractorFactory: Factory for creating extractors dynamically
"""

from app.services.extracted.services.extraction.base_extractor import BaseExtractor
from app.services.extracted.services.extraction.extractor_factory import ExtractorFactory
from app.services.enriched.services.entity.resolver import EntityResolver
from app.services.extracted.services.extraction.section import (
    SectionExtractionOrchestrator,
    SectionExtractionResult,
    DocumentExtractionResult,
)

__all__ = [
    "BaseExtractor",
    "ExtractorFactory",
    "EntityResolver",
    "SectionExtractionOrchestrator",
    "SectionExtractionResult",
    "DocumentExtractionResult",
]
