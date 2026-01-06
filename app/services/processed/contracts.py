"""Contracts (input/output schemas) for Processed stage."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class DocumentProfile:
    """Document-level classification from page analysis."""
    document_type: str
    document_subtype: Optional[str]
    confidence: float
    section_boundaries: list[dict]


@dataclass
class PageManifest:
    """Output from analyze_pages service."""
    document_id: str
    total_pages: int
    pages_to_process: list[int]
    pages_skipped: list[int]
    processing_ratio: float
    document_profile: DocumentProfile
    page_section_map: dict[int, str]


@dataclass
class OCRResult:
    """Output from run_ocr service."""
    page_count: int
    has_section_metadata: bool


@dataclass
class TableResult:
    """Output from extract_tables service."""
    tables_found: int
    tables_processed: int
    sov_items: int
    loss_run_claims: int


@dataclass
class ChunkResult:
    """Output from chunk_pages service."""
    chunk_count: int
    super_chunk_count: int
    sections_detected: list[str]
    total_tokens: int
