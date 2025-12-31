"""Data models for hybrid chunking and section super-chunks.

This module defines the data structures used for v2 section-aware chunking
with Docling's HybridChunker integration.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum


class SectionType(str, Enum):
    """High-level insurance document section types.
    
    These correspond to the v2 architecture's semantic section groupings.
    """
    DECLARATIONS = "declarations"
    DEFINITIONS = "definitions"
    COVERAGES = "coverages"
    CONDITIONS = "conditions"
    EXCLUSIONS = "exclusions"
    ENDORSEMENTS = "endorsements"
    SCHEDULE_OF_VALUES = "schedule_of_values"
    LOSS_RUN = "loss_run"
    INSURING_AGREEMENT = "insuring_agreement"
    PREMIUM_SUMMARY = "premium_summary"
    FINANCIAL_STATEMENT = "financial_statement"
    UNKNOWN = "unknown"


class ChunkRole(str, Enum):
    """Role classification for chunks based on content type."""
    TEXT = "text"
    TABLE = "table"
    MIXED = "mixed"
    HEADER = "header"
    FOOTER = "footer"


@dataclass
class HybridChunkMetadata:
    """Extended metadata for hybrid chunks with section awareness.
    
    Attributes:
        document_id: ID of the source document
        page_number: Starting page number (1-indexed)
        page_range: Range of pages covered by this chunk
        section_type: High-level section type
        section_name: Human-readable section name
        subsection_type: Fine-grained subsection classification
        chunk_index: Index within the section
        token_count: Estimated token count
        start_char: Starting character position
        end_char: Ending character position
        stable_chunk_id: Deterministic ID for tracking
        chunk_role: Content type (text, table, mixed)
        has_tables: Whether chunk contains tables
        table_count: Number of tables in chunk
        context_header: Hierarchical context for embedding
        source: Origin of the chunk (docling, pdfplumber, etc.)
    """
    
    document_id: Optional[UUID] = None
    page_number: int = 1
    page_range: List[int] = field(default_factory=list)
    section_type: Optional[SectionType] = None
    section_name: Optional[str] = None
    subsection_type: Optional[str] = None
    chunk_index: int = 0
    token_count: int = 0
    start_char: int = 0
    end_char: int = 0
    stable_chunk_id: Optional[str] = None
    chunk_role: ChunkRole = ChunkRole.TEXT
    has_tables: bool = False
    table_count: int = 0
    context_header: Optional[str] = None
    source: str = "docling"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for serialization."""
        return {
            "document_id": str(self.document_id) if self.document_id else None,
            "page_number": self.page_number,
            "page_range": self.page_range,
            "section_type": self.section_type.value if self.section_type else None,
            "section_name": self.section_name,
            "subsection_type": self.subsection_type,
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "stable_chunk_id": self.stable_chunk_id,
            "chunk_role": self.chunk_role.value,
            "has_tables": self.has_tables,
            "table_count": self.table_count,
            "context_header": self.context_header,
            "source": self.source,
        }


@dataclass
class HybridChunk:
    """Represents a hybrid chunk with text and enriched metadata.
    
    Attributes:
        text: The actual text content
        contextualized_text: Text with hierarchical context prepended
        metadata: Extended chunk metadata
    """
    
    text: str
    contextualized_text: Optional[str] = None
    metadata: HybridChunkMetadata = field(default_factory=HybridChunkMetadata)
    
    def __len__(self) -> int:
        """Return length of text content."""
        return len(self.text)
    
    def __str__(self) -> str:
        """Return string representation."""
        section = self.metadata.section_type.value if self.metadata.section_type else "unknown"
        return (
            f"HybridChunk(section={section}, "
            f"page={self.metadata.page_number}, "
            f"index={self.metadata.chunk_index}, "
            f"tokens={self.metadata.token_count})"
        )
    
    def get_embedding_text(self) -> str:
        """Get text suitable for embedding (contextualized if available)."""
        return self.contextualized_text or self.text


@dataclass
class SectionSuperChunk:
    """Represents a super-chunk grouping multiple chunks by section.
    
    Super-chunks aggregate related chunks for batch LLM processing,
    reducing fragmentation and improving extraction accuracy.
    
    Attributes:
        section_type: The section type for this super-chunk
        section_name: Human-readable section name
        chunks: List of HybridChunks in this super-chunk
        page_range: Range of pages covered
        total_tokens: Total tokens across all chunks
        document_id: Parent document ID
        super_chunk_id: Unique identifier for this super-chunk
        processing_priority: Priority for LLM processing (lower = higher priority)
        requires_llm: Whether this section requires LLM processing
        table_only: Whether this section should use table extraction only
    """
    
    section_type: SectionType
    section_name: str
    chunks: List[HybridChunk] = field(default_factory=list)
    page_range: List[int] = field(default_factory=list)
    total_tokens: int = 0
    document_id: Optional[UUID] = None
    super_chunk_id: Optional[str] = None
    processing_priority: int = 5
    requires_llm: bool = True
    table_only: bool = False
    
    def __post_init__(self):
        """Calculate derived fields after initialization."""
        if self.chunks and not self.total_tokens:
            self.total_tokens = sum(c.metadata.token_count for c in self.chunks)
        if self.chunks and not self.page_range:
            pages = set()
            for chunk in self.chunks:
                pages.add(chunk.metadata.page_number)
                pages.update(chunk.metadata.page_range)
            self.page_range = sorted(pages)
    
    def add_chunk(self, chunk: HybridChunk) -> None:
        """Add a chunk to this super-chunk."""
        self.chunks.append(chunk)
        self.total_tokens += chunk.metadata.token_count
        self.page_range = sorted(set(self.page_range) | 
                                 {chunk.metadata.page_number} | 
                                 set(chunk.metadata.page_range))
    
    def get_combined_text(self, separator: str = "\n\n") -> str:
        """Get combined text from all chunks."""
        return separator.join(c.text for c in self.chunks)
    
    def get_contextualized_text(self, separator: str = "\n\n") -> str:
        """Get combined contextualized text from all chunks."""
        return separator.join(c.get_embedding_text() for c in self.chunks)
    
    def __len__(self) -> int:
        """Return number of chunks in super-chunk."""
        return len(self.chunks)
    
    def __str__(self) -> str:
        """Return string representation."""
        return (
            f"SectionSuperChunk(section={self.section_type.value}, "
            f"chunks={len(self.chunks)}, "
            f"tokens={self.total_tokens}, "
            f"pages={self.page_range})"
        )


@dataclass
class ChunkingResult:
    """Result of the hybrid chunking process.
    
    Attributes:
        chunks: List of all hybrid chunks
        super_chunks: Section-grouped super-chunks
        total_tokens: Total tokens across all chunks
        total_pages: Number of pages processed
        section_map: Mapping of section types to chunk counts
        statistics: Processing statistics
    """
    
    chunks: List[HybridChunk] = field(default_factory=list)
    super_chunks: List[SectionSuperChunk] = field(default_factory=list)
    total_tokens: int = 0
    total_pages: int = 0
    section_map: Dict[str, int] = field(default_factory=dict)
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    def get_super_chunk_by_section(
        self, 
        section_type: SectionType
    ) -> Optional[SectionSuperChunk]:
        """Get super-chunk for a specific section type."""
        for sc in self.super_chunks:
            if sc.section_type == section_type:
                return sc
        return None
    
    def get_llm_required_super_chunks(self) -> List[SectionSuperChunk]:
        """Get super-chunks that require LLM processing."""
        return [sc for sc in self.super_chunks if sc.requires_llm]
    
    def get_table_only_super_chunks(self) -> List[SectionSuperChunk]:
        """Get super-chunks that should use table extraction only."""
        return [sc for sc in self.super_chunks if sc.table_only]


# Section processing configuration
# max_chunks: Maximum number of chunks per super-chunk (soft limit)
# max_tokens: Maximum tokens per super-chunk (hard limit for LLM context)
# priority: Processing priority (lower = higher priority)
# requires_llm: Whether section needs LLM extraction
# table_only: Whether section should only use table extraction
SECTION_CONFIG = {
    SectionType.DECLARATIONS: {
        "max_chunks": 3,
        "max_tokens": 4000,
        "priority": 1,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.COVERAGES: {
        "max_chunks": 8,
        "max_tokens": 6000,
        "priority": 2,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.CONDITIONS: {
        "max_chunks": 5,
        "max_tokens": 5000,
        "priority": 3,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.EXCLUSIONS: {
        "max_chunks": 5,
        "max_tokens": 5000,
        "priority": 3,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.ENDORSEMENTS: {
        "max_chunks": 10,  # 1 per endorsement
        "max_tokens": 5000,
        "priority": 4,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.SCHEDULE_OF_VALUES: {
        "max_chunks": 5,
        "max_tokens": 5000,
        "priority": 2,
        "requires_llm": False,
        "table_only": True,
    },
    SectionType.LOSS_RUN: {
        "max_chunks": 5,
        "max_tokens": 5000,
        "priority": 2,
        "requires_llm": False,
        "table_only": True,
    },
    SectionType.INSURING_AGREEMENT: {
        "max_chunks": 3,
        "max_tokens": 4000,
        "priority": 2,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.PREMIUM_SUMMARY: {
        "max_chunks": 3,
        "max_tokens": 4000,
        "priority": 3,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.FINANCIAL_STATEMENT: {
        "max_chunks": 5,
        "max_tokens": 5000,
        "priority": 4,
        "requires_llm": True,
        "table_only": False,
    },
    SectionType.UNKNOWN: {
        "max_chunks": 5,
        "max_tokens": 5000,
        "priority": 10,
        "requires_llm": True,
        "table_only": False,
    },
}

