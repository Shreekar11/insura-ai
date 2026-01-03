"""Contracts (input/output schemas) for Classified stage."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassificationSchema:
    """Schema for classification results."""
    document_id: str
    classified_type: str
    confidence: float
    document_subtype: Optional[str] = None
    decision_details: Optional[dict] = None
