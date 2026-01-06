"""Contracts (input/output schemas) for Extracted stage."""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class SectionExtractionResult:
    """Result from section field extraction."""
    section_name: str
    extracted_data: Dict[str, Any]
    confidence: float


@dataclass
class EntityExtractionResult:
    """Result from entity extraction."""
    total_entities: int
    entity_types: List[str]
    extraction_details: Dict[str, Any]
