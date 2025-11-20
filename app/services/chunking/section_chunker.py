"""Section-aware chunking implementation.

This module handles splitting pages into section-level chunks based on
insurance document structure.
"""

import re
from typing import List, Optional, Tuple

from app.services.chunking.models import ChunkMetadata, TextChunk
from app.services.chunking.token_counter import TokenCounter
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class SectionChunker:
    """Section-aware chunker for insurance documents.
    
    This chunker detects common insurance document sections and splits
    pages into semantic chunks based on section boundaries.
    """
    
    # Insurance document section patterns
    SECTION_PATTERNS = [
        (r'^(DECLARATIONS?)\s*$', 'Declarations'),
        (r'^(INSURING AGREEMENT)\s*$', 'Insuring Agreement'),
        (r'^(ENDORSEMENTS?)\s*$', 'Endorsements'),
        (r'^(EXCLUSIONS?)\s*$', 'Exclusions'),
        (r'^(COVERAGE|COVERAGES)\s*.*$', 'Coverage'),
        (r'^(SCHEDULE OF VALUES|SOV)\s*$', 'Schedule of Values'),
        (r'^(LOSS (HISTORY|RUNS?))\s*$', 'Loss History'),
        (r'^(FINANCIAL STATEMENT)\s*$', 'Financial Statement'),
        (r'^(PREMIUM SUMMARY)\s*$', 'Premium Summary'),
        (r'^(POLICY (NUMBER|PERIOD|DETAILS))\s*.*$', 'Policy Details'),
        (r'^(INSURED|NAMED INSURED)\s*.*$', 'Insured Information'),
        (r'^(SECTION [IVX\d]+)', 'Section'),
        (r'^(PART [IVX\d]+)', 'Part'),
        # Markdown-style headers
        (r'^#{1,3}\s+(.+)$', None),  # Will use captured group as section name
    ]
    
    # Patterns that indicate structural boundaries
    BOUNDARY_PATTERNS = [
        r'^={3,}\s*$',  # === separator
        r'^-{3,}\s*$',  # --- separator
        r'^_{3,}\s*$',  # ___ separator
    ]
    
    def __init__(
        self,
        token_counter: Optional[TokenCounter] = None,
        max_tokens_per_chunk: int = 1500,
        overlap_tokens: int = 50
    ):
        """Initialize section chunker.
        
        Args:
            token_counter: Token counter instance (creates new if None)
            max_tokens_per_chunk: Maximum tokens per chunk
            overlap_tokens: Number of tokens to overlap between chunks
        """
        self.token_counter = token_counter or TokenCounter()
        self.max_tokens_per_chunk = max_tokens_per_chunk
        self.overlap_tokens = overlap_tokens
        LOGGER.info(
            f"Initialized section chunker with max {max_tokens_per_chunk} tokens, "
            f"overlap {overlap_tokens} tokens"
        )
    
    def chunk_by_sections(
        self,
        page_chunk: TextChunk
    ) -> List[TextChunk]:
        """Split a page chunk into section-level chunks.
        
        Args:
            page_chunk: Page-level chunk to split
            
        Returns:
            List[TextChunk]: List of section-level chunks
        """
        if not page_chunk.text:
            return []
        
        # If page is already under token limit, return as-is
        if page_chunk.metadata.token_count <= self.max_tokens_per_chunk:
            LOGGER.debug(
                f"Page {page_chunk.metadata.page_number} already under token limit"
            )
            return [page_chunk]
        
        LOGGER.info(
            f"Splitting page {page_chunk.metadata.page_number} into sections "
            f"({page_chunk.metadata.token_count} tokens)"
        )
        
        # Detect sections
        sections = self._detect_sections(page_chunk.text)
        
        if not sections:
            # No sections found, split by token limit only
            LOGGER.warning(
                f"No sections detected in page {page_chunk.metadata.page_number}, "
                "using token-based splitting"
            )
            return self._split_by_tokens(page_chunk)
        
        # Create chunks from sections
        chunks = []
        for idx, (section_name, section_text, start_pos, end_pos) in enumerate(sections):
            section_tokens = self.token_counter.count_tokens(section_text)
            
            # If section exceeds limit, split it further
            if section_tokens > self.max_tokens_per_chunk:
                LOGGER.debug(
                    f"Section '{section_name}' exceeds limit ({section_tokens} tokens), "
                    "splitting further"
                )
                sub_chunks = self._split_section_by_tokens(
                    section_text,
                    section_name,
                    page_chunk.metadata.page_number,
                    page_chunk.metadata.document_id,
                    idx
                )
                chunks.extend(sub_chunks)
            else:
                metadata = ChunkMetadata(
                    document_id=page_chunk.metadata.document_id,
                    page_number=page_chunk.metadata.page_number,
                    section_name=section_name,
                    chunk_index=idx,
                    token_count=section_tokens,
                    start_char=start_pos,
                    end_char=end_pos
                )
                chunk = TextChunk(text=section_text, metadata=metadata)
                chunks.append(chunk)
        
        LOGGER.info(
            f"Split page {page_chunk.metadata.page_number} into {len(chunks)} section chunks"
        )
        return chunks
    
    def _detect_sections(self, text: str) -> List[Tuple[str, str, int, int]]:
        """Detect sections in text.
        
        Args:
            text: Page text
            
        Returns:
            List of (section_name, section_text, start_pos, end_pos) tuples
        """
        sections = []
        lines = text.split('\n')
        current_section_name = "Unknown"
        current_section_lines = []
        current_start_pos = 0
        char_position = 0
        
        for line_idx, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Check if this line is a section header
            section_name = self._match_section_header(line_stripped)
            
            if section_name:
                # Save previous section if it exists
                if current_section_lines:
                    section_text = '\n'.join(current_section_lines).strip()
                    if section_text:
                        sections.append((
                            current_section_name,
                            section_text,
                            current_start_pos,
                            char_position
                        ))
                
                # Start new section
                current_section_name = section_name
                current_section_lines = []
                current_start_pos = char_position + len(line) + 1  # +1 for newline
            else:
                # Add line to current section
                current_section_lines.append(line)
            
            char_position += len(line) + 1  # +1 for newline
        
        # Add final section
        if current_section_lines:
            section_text = '\n'.join(current_section_lines).strip()
            if section_text:
                sections.append((
                    current_section_name,
                    section_text,
                    current_start_pos,
                    char_position
                ))
        
        return sections
    
    def _match_section_header(self, line: str) -> Optional[str]:
        """Check if line matches a section header pattern.
        
        Args:
            line: Line to check
            
        Returns:
            Section name if matched, None otherwise
        """
        if not line:
            return None
        
        # Check against all section patterns
        for pattern, section_name in self.SECTION_PATTERNS:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                # If section_name is None, use captured group
                if section_name is None and match.groups():
                    return match.group(1).strip()
                return section_name
        
        # Check if line is all caps (likely a header)
        if line.isupper() and len(line.split()) <= 5:
            return line.title()
        
        return None
    
    def _split_by_tokens(self, page_chunk: TextChunk) -> List[TextChunk]:
        """Split page chunk by token limit only.
        
        Args:
            page_chunk: Page chunk to split
            
        Returns:
            List of chunks split by token limit
        """
        text_chunks = self.token_counter.split_by_token_limit(
            page_chunk.text,
            self.max_tokens_per_chunk,
            self.overlap_tokens
        )
        
        chunks = []
        for idx, text in enumerate(text_chunks):
            metadata = ChunkMetadata(
                document_id=page_chunk.metadata.document_id,
                page_number=page_chunk.metadata.page_number,
                section_name=None,
                chunk_index=idx,
                token_count=self.token_counter.count_tokens(text),
                start_char=0,
                end_char=len(text)
            )
            chunk = TextChunk(text=text, metadata=metadata)
            chunks.append(chunk)
        
        return chunks
    
    def _split_section_by_tokens(
        self,
        section_text: str,
        section_name: str,
        page_number: int,
        document_id: Optional[str],
        base_index: int
    ) -> List[TextChunk]:
        """Split a large section by token limit.
        
        Args:
            section_text: Section text to split
            section_name: Name of the section
            page_number: Page number
            document_id: Document ID
            base_index: Base chunk index
            
        Returns:
            List of sub-chunks
        """
        text_chunks = self.token_counter.split_by_token_limit(
            section_text,
            self.max_tokens_per_chunk,
            self.overlap_tokens
        )
        
        chunks = []
        for idx, text in enumerate(text_chunks):
            metadata = ChunkMetadata(
                document_id=document_id,
                page_number=page_number,
                section_name=f"{section_name} (Part {idx + 1})",
                chunk_index=base_index + idx,
                token_count=self.token_counter.count_tokens(text),
                start_char=0,
                end_char=len(text)
            )
            chunk = TextChunk(text=text, metadata=metadata)
            chunks.append(chunk)
        
        return chunks
