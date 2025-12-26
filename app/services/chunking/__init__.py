"""Chunking service package.

This package provides utilities for chunking large insurance documents
into smaller pieces that fit within LLM token limits.

v2 Architecture additions:
- HybridChunkingService: Docling-based hybrid chunking with section awareness
- SectionSuperChunkBuilder: Creates section super-chunks for batch LLM processing
- New models for hybrid chunks and section super-chunks
"""

from app.services.chunking.chunking_service import ChunkingService
from app.services.chunking.models import ChunkMetadata, NormalizedChunk, TextChunk
from app.services.chunking.page_chunker import PageChunker
from app.services.chunking.section_chunker import SectionChunker
from app.services.chunking.token_counter import TokenCounter

# v2 hybrid chunking components
from app.services.chunking.hybrid_models import (
    SectionType,
    ChunkRole,
    HybridChunk,
    HybridChunkMetadata,
    SectionSuperChunk,
    ChunkingResult,
    SECTION_CONFIG,
)
from app.services.chunking.hybrid_chunking_service import HybridChunkingService
from app.services.chunking.section_super_chunk_builder import (
    SectionSuperChunkBuilder,
    SuperChunkBatch,
)

__all__ = [
    # v1 components
    "ChunkingService",
    "TextChunk",
    "ChunkMetadata",
    "NormalizedChunk",
    "PageChunker",
    "SectionChunker",
    "TokenCounter",
    # v2 hybrid chunking
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
