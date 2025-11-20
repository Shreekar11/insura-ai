"""Page-level chunking implementation.

This module handles splitting documents into page-level chunks.
"""

import re
from typing import List, Optional
from uuid import UUID

from app.services.chunking.models import ChunkMetadata, TextChunk
from app.services.chunking.token_counter import TokenCounter
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class PageChunker:
    """Page-level chunker for insurance documents.
    
    This chunker splits documents by page boundaries, which are natural
    divisions in PDF documents. Each page becomes a separate chunk.
    """
    
    # Common page markers in OCR output
    PAGE_MARKERS = [
        r'Page\s+(\d+)',
        r'Page\s+(\d+)\s+of\s+\d+',
        r'===\s*PAGE\s+(\d+)\s*===',
        r'---\s*Page\s+(\d+)\s*---',
    ]
    
    def __init__(
        self,
        token_counter: Optional[TokenCounter] = None,
        max_tokens_per_chunk: int = 1500
    ):
        """Initialize page chunker.
        
        Args:
            token_counter: Token counter instance (creates new if None)
            max_tokens_per_chunk: Maximum tokens per chunk
        """
        self.token_counter = token_counter or TokenCounter()
        self.max_tokens_per_chunk = max_tokens_per_chunk
        LOGGER.info(f"Initialized page chunker with max {max_tokens_per_chunk} tokens")
    
    def chunk_by_pages(
        self,
        text: str,
        document_id: Optional[UUID] = None
    ) -> List[TextChunk]:
        """Split text into page-level chunks.
        
        Args:
            text: Full document text
            document_id: Optional document ID for metadata
            
        Returns:
            List[TextChunk]: List of page-level chunks
        """
        if not text:
            LOGGER.warning("Empty text provided for page chunking")
            return []
        
        # Try to detect page boundaries
        pages = self._detect_pages(text)
        
        if not pages:
            # No page markers found, treat entire text as single page
            LOGGER.info("No page markers found, treating as single page")
            pages = [(1, text)]
        
        chunks = []
        for page_number, page_text in pages:
            # Check if page exceeds token limit
            token_count = self.token_counter.count_tokens(page_text)
            
            if token_count > self.max_tokens_per_chunk:
                LOGGER.warning(
                    f"Page {page_number} exceeds token limit ({token_count} > {self.max_tokens_per_chunk}). "
                    "Will need section-aware chunking."
                )
            
            metadata = ChunkMetadata(
                document_id=document_id,
                page_number=page_number,
                section_name=None,
                chunk_index=0,
                token_count=token_count,
                start_char=0,
                end_char=len(page_text)
            )
            
            chunk = TextChunk(text=page_text, metadata=metadata)
            chunks.append(chunk)
        
        LOGGER.info(f"Created {len(chunks)} page-level chunks")
        return chunks
    
    def _detect_pages(self, text: str) -> List[tuple[int, str]]:
        """Detect page boundaries in text.
        
        Args:
            text: Full document text
            
        Returns:
            List of (page_number, page_text) tuples
        """
        pages = []
        
        # Try each page marker pattern
        for pattern in self.PAGE_MARKERS:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if matches:
                LOGGER.debug(f"Found {len(matches)} page markers with pattern: {pattern}")
                pages = self._split_by_markers(text, matches)
                break
        
        return pages
    
    def _split_by_markers(
        self,
        text: str,
        matches: List[re.Match]
    ) -> List[tuple[int, str]]:
        """Split text by page marker matches.
        
        Args:
            text: Full document text
            matches: List of regex matches for page markers
            
        Returns:
            List of (page_number, page_text) tuples
        """
        pages = []
        
        for i, match in enumerate(matches):
            page_number = int(match.group(1))
            start_pos = match.end()
            
            # Find end position (start of next page or end of text)
            if i < len(matches) - 1:
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)
            
            page_text = text[start_pos:end_pos].strip()
            
            if page_text:
                pages.append((page_number, page_text))
        
        # If no pages found, check if there's text before first marker
        if not pages and matches:
            first_marker_pos = matches[0].start()
            if first_marker_pos > 0:
                pre_text = text[:first_marker_pos].strip()
                if pre_text:
                    pages.insert(0, (1, pre_text))
        
        return pages
    
    def extract_page_number_from_text(self, text: str) -> Optional[int]:
        """Extract page number from text if present.
        
        Args:
            text: Text to search for page number
            
        Returns:
            Page number if found, None otherwise
        """
        for pattern in self.PAGE_MARKERS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None
