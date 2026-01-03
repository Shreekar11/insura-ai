"""Contracts (input/output schemas) for Summarized stage."""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class SummaryResult:
    """Result from document summarization."""
    summary_text: str
    key_points: List[str]
    metadata: Dict[str, Any]


@dataclass
class EmbeddingResult:
    """Result from vector embedding generation."""
    vector_dimension: int
    chunks_embedded: int
    storage_details: Dict[str, Any]
