"""Main chunking service orchestrator.

This module provides the main ChunkingService class that coordinates
page-level and section-aware chunking.
"""

from typing import List, Optional
from uuid import UUID

from app.services.processed.services.chunking.models import ChunkMetadata, TextChunk
from app.services.processed.services.chunking.token_counter import TokenCounter
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ChunkingService:
    """Main service for chunking insurance documents.
    
    This service orchestrates the dual-layer chunking strategy:
    1. Page-level chunking (base layer)
    2. Section-aware chunking (semantic layer)
    
    It ensures all chunks stay within token limits and maintains
    proper metadata for downstream processing.
    """
    
    def __init__(
        self,
        max_tokens_per_chunk: int = 1500,
        overlap_tokens: int = 50,
        enable_section_chunking: bool = True
    ):
        """Initialize chunking service.
        
        Args:
            max_tokens_per_chunk: Maximum tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks
            enable_section_chunking: Whether to use section-aware chunking
        """
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self.overlap_tokens = overlap_tokens
        self.enable_section_chunking = enable_section_chunking
        
        # Initialize components
        self.token_counter = TokenCounter()
        
        LOGGER.info(
            "Initialized chunking service",
            extra={
                "max_tokens": max_tokens_per_chunk,
                "overlap": overlap_tokens,
                "section_chunking": enable_section_chunking
            }
        )
    
    def chunk_document(
        self,
        text: str,
        document_id: Optional[UUID] = None,
        initial_page_number: int = 1
    ) -> List[TextChunk]:
        """Chunk a document using dual-layer strategy.
        
        This is the main entry point for chunking. It:
        1. Splits document into pages
        2. Applies section-aware chunking to pages that exceed token limit
        3. Returns all chunks in order
        
        Args:
            text: Full document text
            document_id: Optional document ID for metadata
            
        Returns:
            List[TextChunk]: List of all chunks in order
            
        Example:
            >>> service = ChunkingService()
            >>> chunks = service.chunk_document(large_text)
            >>> for chunk in chunks:
            ...     print(f"Page {chunk.metadata.page_number}, "
            ...           f"Section: {chunk.metadata.section_name}, "
            ...           f"Tokens: {chunk.metadata.token_count}")
        """
        if not text:
            LOGGER.warning("Empty text provided for chunking")
            return []
        
        # Check if chunking is needed
        total_tokens = self.token_counter.count_tokens(text)
        LOGGER.info(
            f"Starting document chunking",
            extra={
                "total_tokens": total_tokens,
                "document_id": str(document_id) if document_id else None
            }
        )
        
        if total_tokens <= self.max_tokens_per_chunk:
            LOGGER.info("Document under token limit, no chunking needed")
            metadata = ChunkMetadata(
                document_id=document_id,
                page_number=initial_page_number,
                section_name=None,
                chunk_index=0,
                token_count=total_tokens,
                start_char=0,
                end_char=len(text)
            )
            return [TextChunk(text=text, metadata=metadata)]
        
        # Layer 1: Page-level chunking
        page_chunks = self.page_chunker.chunk_by_pages(
            text, 
            document_id,
            initial_page_number=initial_page_number
        )
        LOGGER.info(f"Created {len(page_chunks)} page-level chunks")
        
        # Layer 2: Section-aware chunking (if enabled)
        if self.enable_section_chunking:
            final_chunks = []
            for page_chunk in page_chunks:
                section_chunks = self.section_chunker.chunk_by_sections(page_chunk)
                final_chunks.extend(section_chunks)
            
            LOGGER.info(
                f"Applied section-aware chunking: {len(page_chunks)} pages -> "
                f"{len(final_chunks)} final chunks"
            )
            return final_chunks
        else:
            return page_chunks
    
    def merge_chunks(
        self,
        chunks: List[TextChunk],
        add_section_markers: bool = True
    ) -> str:
        """Merge chunks back into a single document.
        
        Args:
            chunks: List of chunks to merge
            add_section_markers: Whether to add section markers
            
        Returns:
            str: Merged document text
        """
        if not chunks:
            return ""
        
        # Sort chunks by page number and chunk index
        sorted_chunks = sorted(
            chunks,
            key=lambda c: (c.metadata.page_number, c.metadata.chunk_index)
        )
        
        merged_parts = []
        current_page = None
        
        for chunk in sorted_chunks:
            # Add page marker if page changed
            if add_section_markers and chunk.metadata.page_number != current_page:
                current_page = chunk.metadata.page_number
                merged_parts.append(f"\n=== PAGE {current_page} ===\n")
            
            # Add section marker if section name exists
            if add_section_markers and chunk.metadata.section_name:
                merged_parts.append(f"\n--- {chunk.metadata.section_name} ---\n")
            
            # Add chunk text
            merged_parts.append(chunk.text)
        
        merged_text = '\n'.join(merged_parts)
        
        # Clean up excessive whitespace
        merged_text = re.sub(r'\n{3,}', '\n\n', merged_text)
        
        LOGGER.info(f"Merged {len(chunks)} chunks into single document")
        return merged_text.strip()
    
    def get_chunk_statistics(self, chunks: List[TextChunk]) -> dict:
        """Get statistics about chunks.
        
        Args:
            chunks: List of chunks
            
        Returns:
            dict: Statistics about the chunks
        """
        if not chunks:
            return {
                "total_chunks": 0,
                "total_tokens": 0,
                "avg_tokens_per_chunk": 0,
                "max_tokens": 0,
                "min_tokens": 0,
                "pages": 0,
                "sections": 0
            }
        
        token_counts = [c.metadata.token_count for c in chunks]
        pages = set(c.metadata.page_number for c in chunks)
        sections = set(c.metadata.section_name for c in chunks if c.metadata.section_name)
        
        stats = {
            "total_chunks": len(chunks),
            "total_tokens": sum(token_counts),
            "avg_tokens_per_chunk": sum(token_counts) / len(chunks),
            "max_tokens": max(token_counts),
            "min_tokens": min(token_counts),
            "pages": len(pages),
            "sections": len(sections),
            "chunks_per_page": len(chunks) / len(pages) if pages else 0
        }
        
        LOGGER.debug("Chunk statistics", extra=stats)
        return stats


# Import re for merge_chunks
import re
