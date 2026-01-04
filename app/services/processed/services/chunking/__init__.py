"""Chunking service package.

This package provides utilities for chunking large insurance documents
into smaller pieces that fit within LLM token limits.

Additions:
- HybridChunkingService: Docling-based hybrid chunking with section awareness
- SectionSuperChunkBuilder: Creates section super-chunks for batch LLM processing
- New models for hybrid chunks and section super-chunks
"""

from .chunking_service import ChunkingService
from .models import ChunkMetadata, NormalizedChunk, TextChunk
from .token_counter import TokenCounter

from .hybrid_models import (
    SectionType,
    ChunkRole,
    HybridChunk,
    HybridChunkMetadata,
    SectionSuperChunk,
    ChunkingResult,
    SECTION_CONFIG,
)
from .hybrid_chunking_service import HybridChunkingService
from .section_super_chunk_builder import (
    SectionSuperChunkBuilder,
    SuperChunkBatch,
)

__all__ = [
    "ChunkingService",
    "TextChunk",
    "ChunkMetadata",
    "NormalizedChunk",
    "TokenCounter",
    "SectionType",
    "ChunkRole",
    "HybridChunk",
    "HybridChunkMetadata",
    "SectionSuperChunk",
    "ChunkingResult",
    "SECTION_CONFIG",
    "HybridChunkingService",
    "SectionSuperChunkBuilder",
    "SuperChunkBatch",
]
