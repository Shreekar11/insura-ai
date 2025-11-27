"""Data models for chunking service.

This module defines the data structures used throughout the chunking pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass
class ChunkMetadata:
    """Metadata for a text chunk.
    
    Attributes:
        document_id: ID of the source document
        page_number: Page number (1-indexed)
        section_name: Name of the section (e.g., "Declarations", "Endorsements")
        chunk_index: Index of this chunk within the page/section
        token_count: Estimated token count
        start_char: Starting character position in original text
        end_char: Ending character position in original text
        stable_chunk_id: Deterministic ID (doc_{id}_p{page}_c{chunk})
        section_type: High-level section type (Declarations, Coverages, etc.)
        subsection_type: Fine-grained subsection (Named Insured, Limits, etc.)
    """
    
    document_id: Optional[UUID] = None
    page_number: int = 1
    section_name: Optional[str] = None
    chunk_index: int = 0
    token_count: int = 0
    start_char: int = 0
    end_char: int = 0
    stable_chunk_id: Optional[str] = None
    section_type: Optional[str] = None
    subsection_type: Optional[str] = None


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata.
    
    Attributes:
        text: The actual text content
        metadata: Chunk metadata
    """
    
    text: str
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)
    
    def __len__(self) -> int:
        """Return length of text content."""
        return len(self.text)
    
    def __str__(self) -> str:
        """Return string representation."""
        return (
            f"TextChunk(page={self.metadata.page_number}, "
            f"section={self.metadata.section_name}, "
            f"index={self.metadata.chunk_index}, "
            f"tokens={self.metadata.token_count})"
        )


@dataclass
class NormalizedChunk:
    """Represents a normalized chunk with original metadata.
    
    Attributes:
        original_chunk: The original text chunk
        normalized_text: The normalized text
        processing_time_ms: Time taken to normalize (milliseconds)
        normalization_method: Method used (llm, hybrid, rule_based)
    """
    
    original_chunk: TextChunk
    normalized_text: str
    processing_time_ms: int = 0
    normalization_method: str = "llm"
    
    @property
    def metadata(self) -> ChunkMetadata:
        """Get metadata from original chunk."""
        return self.original_chunk.metadata
    
    def __str__(self) -> str:
        """Return string representation."""
        return (
            f"NormalizedChunk(page={self.metadata.page_number}, "
            f"section={self.metadata.section_name}, "
            f"method={self.normalization_method})"
        )
