"""Hybrid chunking service using Docling's HybridChunker.

This service implements v2 section-aware + layout-aware chunking:
- Uses Docling's HybridChunker for tokenization-aware splitting
- Preserves document structure and hierarchy
- Creates semantically meaningful chunks for LLM processing
- Supports context enrichment for better embeddings
"""

import re
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.services.processed.services.chunking.hybrid_models import (
    HybridChunk,
    HybridChunkMetadata,
    SectionType,
    ChunkRole,
    SectionSuperChunk,
    ChunkingResult,
    SECTION_CONFIG,
)
from app.services.processed.services.chunking.token_counter import TokenCounter
from app.services.processed.services.chunking.section_super_chunk_builder import SectionSuperChunkBuilder
from app.models.page_data import PageData
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Section anchor patterns for detecting section boundaries
SECTION_ANCHORS = {
    SectionType.DECLARATIONS: [
        r'^\s*DECLARATIONS?\s*$',
        r'^\s*POLICY\s+DECLARATIONS?\s*$',
        r'^\s*COMMON\s+POLICY\s+DECLARATIONS?\s*$',
    ],
    SectionType.COVERAGES: [
        r'^\s*COVERAGES?\s*$',
        r'^\s*COVERAGE\s+FORM\s*$',
        r'^\s*COVERAGE\s+[A-Z]\s*[-:]',
        r'^\s*PROPERTY\s+COVERAGE\s*$',
        r'^\s*LIABILITY\s+COVERAGE\s*$',
    ],
    SectionType.CONDITIONS: [
        r'^\s*CONDITIONS?\s*$',
        r'^\s*GENERAL\s+CONDITIONS?\s*$',
        r'^\s*POLICY\s+CONDITIONS?\s*$',
        r'^\s*COMMERCIAL\s+PROPERTY\s+CONDITIONS?\s*$',
    ],
    SectionType.EXCLUSIONS: [
        r'^\s*EXCLUSIONS?\s*$',
        r'^\s*GENERAL\s+EXCLUSIONS?\s*$',
        r'^\s*WHAT\s+IS\s+NOT\s+COVERED\s*$',
    ],
    SectionType.ENDORSEMENTS: [
        r'^\s*ENDORSEMENTS?\s*$',
        r'^\s*ENDORSEMENT\s+NO\.?\s*\d*',
        r'^\s*POLICY\s+ENDORSEMENTS?\s*$',
        r'^\s*FORMS?\s+AND\s+ENDORSEMENTS?\s*$',
    ],
    SectionType.SCHEDULE_OF_VALUES: [
        r'^\s*SCHEDULE\s+OF\s+VALUES?\s*$',
        r'^\s*SOV\s*$',
        r'^\s*PROPERTY\s+SCHEDULE\s*$',
        r'^\s*LOCATION\s+SCHEDULE\s*$',
    ],
    SectionType.LOSS_RUN: [
        r'^\s*LOSS\s+RUN\s*$',
        r'^\s*LOSS\s+HISTORY\s*$',
        r'^\s*LOSS\s+EXPERIENCE\s*$',
        r'^\s*CLAIMS?\s+HISTORY\s*$',
    ],
    SectionType.INSURING_AGREEMENT: [
        r'^\s*INSURING\s+AGREEMENT\s*$',
        r'^\s*AGREEMENT\s*$',
    ],
    SectionType.PREMIUM_SUMMARY: [
        r'^\s*PREMIUM\s+SUMMARY\s*$',
        r'^\s*PREMIUM\s+SCHEDULE\s*$',
        r'^\s*PREMIUM\s+BREAKDOWN\s*$',
    ],
    SectionType.FINANCIAL_STATEMENT: [
        r'^\s*FINANCIAL\s+STATEMENT\s*$',
        r'^\s*FINANCIAL\s+INFORMATION\s*$',
    ],
}


class HybridChunkingService:
    """Service for hybrid chunking of documents.
    
    This service uses Docling's HybridChunker. It provides:
    - Tokenization-aware chunk splitting
    - Section boundary detection
    - Context enrichment for embeddings
    - Super-chunk aggregation by section with token limits
    
    Attributes:
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Token overlap between chunks
        tokenizer: Tokenizer name for HybridChunker
        token_counter: Token counting utility
        max_tokens_per_super_chunk: Maximum tokens per super-chunk (for LLM limits)
    """
    
    # Default super-chunk limits for LLM processing
    DEFAULT_MAX_TOKENS_PER_SUPER_CHUNK = 6000
    
    def __init__(
        self,
        max_tokens: int = 1500,
        overlap_tokens: int = 50,
        tokenizer: str = "sentence-transformers/all-MiniLM-L6-v2",
        merge_peers: bool = True,
        max_tokens_per_super_chunk: int = DEFAULT_MAX_TOKENS_PER_SUPER_CHUNK,
    ):
        """Initialize hybrid chunking service.
        
        Args:
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Token overlap between chunks
            tokenizer: HuggingFace tokenizer name for HybridChunker
            merge_peers: Whether to merge small sibling chunks
            max_tokens_per_super_chunk: Maximum tokens per super-chunk for LLM calls
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.tokenizer = tokenizer
        self.merge_peers = merge_peers
        self.max_tokens_per_super_chunk = max_tokens_per_super_chunk
        self.token_counter = TokenCounter()
        self._docling_chunker = None
        self._super_chunk_builder = SectionSuperChunkBuilder(
            max_tokens_per_super_chunk=max_tokens_per_super_chunk,
        )
        self._init_docling_chunker()
        
        LOGGER.info(
            "Initialized HybridChunkingService",
            extra={
                "max_tokens": max_tokens,
                "overlap_tokens": overlap_tokens,
                "max_tokens_per_super_chunk": max_tokens_per_super_chunk,
                "tokenizer": tokenizer,
                "docling_available": self._docling_chunker is not None,
            }
        )
    
    def _init_docling_chunker(self) -> None:
        """Initialize Docling HybridChunker if available."""
        try:
            from docling.chunking import HybridChunker
            self._docling_chunker = HybridChunker(
                tokenizer=self.tokenizer,
                max_tokens=self.max_tokens,
                merge_peers=self.merge_peers,
            )
            LOGGER.info("Docling HybridChunker initialized successfully")
        except ImportError as e:
            LOGGER.warning(
                f"Docling HybridChunker not available, using fallback: {e}"
            )
            self._docling_chunker = None
        except Exception as e:
            LOGGER.error(
                f"Failed to initialize Docling HybridChunker: {e}",
                exc_info=True
            )
            self._docling_chunker = None
    
    def chunk_pages(
        self,
        pages: List[PageData],
        document_id: Optional[UUID] = None,
        page_section_map: Optional[Dict[int, str]] = None,
    ) -> ChunkingResult:
        """Chunk document pages using hybrid strategy.
        
        This method:
        1. Uses page_section_map from manifest OR detects sections from content
        2. Creates hybrid chunks with section awareness
        3. Builds section super-chunks for batch processing
        
        Args:
            pages: List of PageData from OCR extraction
            document_id: Optional document ID for metadata
            page_section_map: Optional mapping of page numbers to section types
                from Phase 0 page analysis. If provided, this is used instead
                of detecting sections from content, ensuring consistency with
                the document profile.
            
        Returns:
            ChunkingResult with chunks and super-chunks
        """
        if not pages:
            LOGGER.warning("Empty pages list provided for chunking")
            return ChunkingResult()
        
        # Check if pages have section metadata from OCR extraction
        has_metadata_sections = any(
            p.metadata and p.metadata.get("page_type") 
            for p in pages
        )
        
        LOGGER.info(
            "Starting hybrid chunking",
            extra={
                "document_id": str(document_id) if document_id else None,
                "page_count": len(pages),
                "has_page_section_map": page_section_map is not None,
                "has_metadata_sections": has_metadata_sections,
            }
        )
        
        # Step 1: Get page sections from manifest, metadata, or detect from content
        if page_section_map:
            # Use section map from manifest (preferred - from Phase 0)
            LOGGER.info("Using page_section_map from manifest for section assignment")
            page_sections = self._convert_section_map(page_section_map)
        elif has_metadata_sections:
            # Use section metadata from OCR extraction
            LOGGER.info("Using page_type metadata from OCR extraction")
            page_sections = self._extract_sections_from_metadata(pages)
        else:
            # Fallback: detect sections from content
            LOGGER.info("Detecting sections from page content (fallback)")
            page_sections = self._detect_page_sections(pages)
        
        # Step 2: Create hybrid chunks
        chunks = self._create_hybrid_chunks(pages, page_sections, document_id)
        
        # Step 3: Build section super-chunks
        super_chunks = self._build_super_chunks(chunks, document_id)
        
        # Step 4: Calculate statistics
        result = self._build_chunking_result(chunks, super_chunks, pages)
        
        LOGGER.info(
            "Hybrid chunking completed",
            extra={
                "document_id": str(document_id) if document_id else None,
                "total_chunks": len(chunks),
                "super_chunks": len(super_chunks),
                "total_tokens": result.total_tokens,
                "sections": list(result.section_map.keys()),
                "section_source": "manifest" if page_section_map else (
                    "metadata" if has_metadata_sections else "content_detection"
                ),
            }
        )
        
        return result
    
    def _convert_section_map(
        self,
        page_section_map: Dict[int, str],
    ) -> Dict[int, SectionType]:
        """Convert page_section_map strings to canonical SectionType enum.
        
        Uses SectionTypeMapper to ensure consistent taxonomy, handling both
        PageType values (e.g., "endorsement", "sov") and SectionType values
        (e.g., "endorsements", "schedule_of_values").
        
        Args:
            page_section_map: Mapping of page numbers to section type strings
            
        Returns:
            Dict mapping page numbers to canonical SectionType enums
        """
        from app.utils.section_type_mapper import SectionTypeMapper
        
        result = {}
        for page_num, section_str in page_section_map.items():
            # Handle both string keys (from JSON) and int keys
            page_key = int(page_num) if isinstance(page_num, str) else page_num
            # Use canonical mapper to normalize section type
            section_type = SectionTypeMapper.string_to_section_type(section_str)
            result[page_key] = section_type
            
            # Log if normalization changed the value
            if section_str.lower() != section_type.value:
                LOGGER.debug(
                    f"Normalized section type for page {page_key}: "
                    f"'{section_str}' -> '{section_type.value}'"
                )
        return result
    
    def _extract_sections_from_metadata(
        self,
        pages: List[PageData],
    ) -> Dict[int, SectionType]:
        """Extract section types from page metadata using canonical mapper.
        
        Args:
            pages: List of pages with metadata
            
        Returns:
            Dict mapping page numbers to canonical SectionType enums
        """
        from app.utils.section_type_mapper import SectionTypeMapper
        
        page_sections = {}
        for page in pages:
            page_type_str = page.metadata.get("page_type") if page.metadata else None
            if page_type_str:
                # Use canonical mapper to normalize section type
                section_type = SectionTypeMapper.string_to_section_type(page_type_str)
                page_sections[page.page_number] = section_type
                
                # Log if normalization changed the value
                if page_type_str.lower() != section_type.value:
                    LOGGER.debug(
                        f"Normalized section type for page {page.page_number} from metadata: "
                        f"'{page_type_str}' -> '{section_type.value}'"
                    )
            else:
                page_sections[page.page_number] = SectionType.UNKNOWN
        return page_sections
    
    def chunk_docling_document(
        self,
        docling_document: Any,
        document_id: Optional[UUID] = None,
    ) -> ChunkingResult:
        """Chunk a Docling document object directly.
        
        This method uses Docling's native HybridChunker for optimal results
        when a DoclingDocument is available.
        
        Args:
            docling_document: Docling Document object
            document_id: Optional document ID for metadata
            
        Returns:
            ChunkingResult with chunks and super-chunks
        """
        if self._docling_chunker is None:
            LOGGER.warning(
                "Docling chunker not available, converting to pages and using fallback"
            )
            # Convert to PageData and use standard chunking
            pages = self._docling_to_pages(docling_document)
            return self.chunk_pages(pages, document_id)
        
        LOGGER.info(
            "Chunking Docling document with native HybridChunker",
            extra={"document_id": str(document_id) if document_id else None}
        )
        
        try:
            # Use Docling's HybridChunker
            chunk_iter = self._docling_chunker.chunk(dl_doc=docling_document)
            
            chunks = []
            for idx, docling_chunk in enumerate(chunk_iter):
                # Get contextualized text for better embeddings
                contextualized = self._docling_chunker.contextualize(chunk=docling_chunk)
                
                # Detect section type from chunk text
                section_type = self._detect_section_type(docling_chunk.text)
                
                # Create metadata
                metadata = HybridChunkMetadata(
                    document_id=document_id,
                    page_number=self._extract_page_number(docling_chunk),
                    section_type=section_type,
                    section_name=section_type.value.replace("_", " ").title(),
                    chunk_index=idx,
                    token_count=self.token_counter.count_tokens(docling_chunk.text),
                    stable_chunk_id=self._generate_stable_id(document_id, idx),
                    context_header=self._extract_context_header(contextualized, docling_chunk.text),
                    source="docling_native",
                )
                
                chunk = HybridChunk(
                    text=docling_chunk.text,
                    contextualized_text=contextualized,
                    metadata=metadata,
                )
                chunks.append(chunk)
            
            # Build super-chunks
            super_chunks = self._build_super_chunks(chunks, document_id)
            
            return self._build_chunking_result(chunks, super_chunks, [])
            
        except Exception as e:
            LOGGER.error(
                f"Docling chunking failed, falling back to page-based: {e}",
                exc_info=True
            )
            pages = self._docling_to_pages(docling_document)
            return self.chunk_pages(pages, document_id)
    
    def _detect_page_sections(
        self,
        pages: List[PageData],
    ) -> Dict[int, SectionType]:
        """Detect section type for each page.
        
        Args:
            pages: List of pages to analyze
            
        Returns:
            Dict mapping page numbers to section types
        """
        page_sections = {}
        current_section = SectionType.UNKNOWN
        
        for page in pages:
            content = page.get_content()
            detected = self._detect_section_type(content)
            
            if detected != SectionType.UNKNOWN:
                current_section = detected
            
            page_sections[page.page_number] = current_section
        
        return page_sections
    
    def _detect_section_type(self, text: str) -> SectionType:
        """Detect section type from text content.
        
        Args:
            text: Text content to analyze
            
        Returns:
            Detected SectionType
        """
        if not text:
            return SectionType.UNKNOWN
        
        # Check first few lines for section headers
        lines = text.split('\n')[:10]
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Remove markdown header markers
            clean_line = re.sub(r'^#+\s*', '', line_stripped)
            
            for section_type, patterns in SECTION_ANCHORS.items():
                for pattern in patterns:
                    # Check both original and cleaned line
                    if re.match(pattern, line_stripped, re.IGNORECASE):
                        return section_type
                    if re.match(pattern, clean_line, re.IGNORECASE):
                        return section_type
        
        return SectionType.UNKNOWN
    
    def _create_hybrid_chunks(
        self,
        pages: List[PageData],
        page_sections: Dict[int, SectionType],
        document_id: Optional[UUID],
    ) -> List[HybridChunk]:
        """Create hybrid chunks from pages with section awareness.
        
        Args:
            pages: List of pages
            page_sections: Mapping of page numbers to sections
            document_id: Document ID for metadata
            
        Returns:
            List of HybridChunks
        """
        chunks = []
        chunk_index = 0
        
        for page in pages:
            content = page.get_content()
            section_type = page_sections.get(page.page_number, SectionType.UNKNOWN)
            
            # Check if page has tables
            has_tables = page.metadata.get("has_tables", False)
            table_count = page.metadata.get("table_count", 0)
            
            # Determine chunk role
            if has_tables and table_count > 0:
                chunk_role = ChunkRole.TABLE if table_count > 2 else ChunkRole.MIXED
            else:
                chunk_role = ChunkRole.TEXT
            
            # Token count for page
            page_tokens = self.token_counter.count_tokens(content)
            
            if page_tokens <= self.max_tokens:
                # Page fits in single chunk
                metadata = HybridChunkMetadata(
                    document_id=document_id,
                    page_number=page.page_number,
                    page_range=[page.page_number],
                    section_type=section_type,
                    section_name=section_type.value.replace("_", " ").title(),
                    chunk_index=chunk_index,
                    token_count=page_tokens,
                    start_char=0,
                    end_char=len(content),
                    stable_chunk_id=self._generate_stable_id(document_id, chunk_index),
                    chunk_role=chunk_role,
                    has_tables=has_tables,
                    table_count=table_count,
                    context_header=self._build_context_header(section_type, page.page_number),
                    source="hybrid_chunker",
                )
                
                chunk = HybridChunk(
                    text=content,
                    contextualized_text=f"{metadata.context_header}\n{content}" if metadata.context_header else content,
                    metadata=metadata,
                )
                chunks.append(chunk)
                chunk_index += 1
            else:
                # Split large page into multiple chunks
                page_chunks = self._split_page_content(
                    content=content,
                    page_number=page.page_number,
                    section_type=section_type,
                    document_id=document_id,
                    base_index=chunk_index,
                    has_tables=has_tables,
                    table_count=table_count,
                )
                chunks.extend(page_chunks)
                chunk_index += len(page_chunks)
        
        return chunks
    
    def _split_page_content(
        self,
        content: str,
        page_number: int,
        section_type: SectionType,
        document_id: Optional[UUID],
        base_index: int,
        has_tables: bool,
        table_count: int,
    ) -> List[HybridChunk]:
        """Split large page content into multiple chunks.
        
        Args:
            content: Page content to split
            page_number: Page number
            section_type: Section type
            document_id: Document ID
            base_index: Starting chunk index
            has_tables: Whether page has tables
            table_count: Number of tables
            
        Returns:
            List of HybridChunks
        """
        chunks = []
        
        # Split by paragraphs first
        paragraphs = self._split_by_paragraphs(content)
        
        current_text = ""
        current_tokens = 0
        chunk_idx = 0
        
        for para in paragraphs:
            para_tokens = self.token_counter.count_tokens(para)
            
            if current_tokens + para_tokens > self.max_tokens:
                # Save current chunk
                if current_text.strip():
                    metadata = HybridChunkMetadata(
                        document_id=document_id,
                        page_number=page_number,
                        page_range=[page_number],
                        section_type=section_type,
                        section_name=f"{section_type.value.replace('_', ' ').title()} (Part {chunk_idx + 1})",
                        chunk_index=base_index + chunk_idx,
                        token_count=current_tokens,
                        stable_chunk_id=self._generate_stable_id(document_id, base_index + chunk_idx),
                        chunk_role=ChunkRole.MIXED if has_tables else ChunkRole.TEXT,
                        has_tables=has_tables,
                        table_count=table_count if chunk_idx == 0 else 0,
                        context_header=self._build_context_header(section_type, page_number),
                        source="hybrid_chunker",
                    )
                    
                    context_header = metadata.context_header or ""
                    chunk = HybridChunk(
                        text=current_text.strip(),
                        contextualized_text=f"{context_header}\n{current_text.strip()}" if context_header else current_text.strip(),
                        metadata=metadata,
                    )
                    chunks.append(chunk)
                    chunk_idx += 1
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap_text(current_text)
                current_text = overlap_text + para
                current_tokens = self.token_counter.count_tokens(current_text)
            else:
                current_text += "\n\n" + para if current_text else para
                current_tokens += para_tokens
        
        # Save final chunk
        if current_text.strip():
            metadata = HybridChunkMetadata(
                document_id=document_id,
                page_number=page_number,
                page_range=[page_number],
                section_type=section_type,
                section_name=f"{section_type.value.replace('_', ' ').title()} (Part {chunk_idx + 1})",
                chunk_index=base_index + chunk_idx,
                token_count=self.token_counter.count_tokens(current_text),
                stable_chunk_id=self._generate_stable_id(document_id, base_index + chunk_idx),
                chunk_role=ChunkRole.MIXED if has_tables else ChunkRole.TEXT,
                has_tables=has_tables,
                context_header=self._build_context_header(section_type, page_number),
                source="hybrid_chunker",
            )
            
            context_header = metadata.context_header or ""
            chunk = HybridChunk(
                text=current_text.strip(),
                contextualized_text=f"{context_header}\n{current_text.strip()}" if context_header else current_text.strip(),
                metadata=metadata,
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs.
        
        Args:
            text: Text to split
            
        Returns:
            List of paragraphs
        """
        # Split on double newlines or markdown headers
        paragraphs = re.split(r'\n\n+|(?=^#{1,3}\s)', text, flags=re.MULTILINE)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _get_overlap_text(self, text: str) -> str:
        """Get overlap text from end of chunk.
        
        Args:
            text: Text to get overlap from
            
        Returns:
            Overlap text
        """
        if not text or self.overlap_tokens <= 0:
            return ""
        
        # Get last few sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        overlap_text = ""
        overlap_tokens = 0
        
        for sentence in reversed(sentences):
            sent_tokens = self.token_counter.count_tokens(sentence)
            if overlap_tokens + sent_tokens > self.overlap_tokens:
                break
            overlap_text = sentence + " " + overlap_text
            overlap_tokens += sent_tokens
        
        return overlap_text.strip() + "\n\n" if overlap_text else ""
    
    def _build_super_chunks(
        self,
        chunks: List[HybridChunk],
        document_id: Optional[UUID],
    ) -> List[SectionSuperChunk]:
        """Build section super-chunks from hybrid chunks with token limits.
        
        Uses SectionSuperChunkBuilder to properly split large sections into
        multiple super-chunks that respect LLM token limits. This prevents
        exceeding max_tokens when sending to LLM APIs.
        
        Args:
            chunks: List of hybrid chunks
            document_id: Document ID
            
        Returns:
            List of SectionSuperChunks, split to respect token limits
        """
        # Use the super-chunk builder which handles token-based splitting
        super_chunks = self._super_chunk_builder.build_super_chunks(
            chunks=chunks,
            document_id=document_id,
        )
        
        LOGGER.debug(
            "Built super-chunks with token limits",
            extra={
                "document_id": str(document_id) if document_id else None,
                "input_chunks": len(chunks),
                "output_super_chunks": len(super_chunks),
                "max_tokens_per_super_chunk": self.max_tokens_per_super_chunk,
                "super_chunk_details": [
                    {
                        "section": sc.section_type.value,
                        "chunks": len(sc.chunks),
                        "tokens": sc.total_tokens,
                    }
                    for sc in super_chunks
                ],
            }
        )
        
        return super_chunks
    
    def _build_chunking_result(
        self,
        chunks: List[HybridChunk],
        super_chunks: List[SectionSuperChunk],
        pages: List[PageData],
    ) -> ChunkingResult:
        """Build final chunking result with statistics.
        
        Args:
            chunks: List of hybrid chunks
            super_chunks: List of super-chunks
            pages: Original pages
            
        Returns:
            ChunkingResult
        """
        total_tokens = sum(c.metadata.token_count for c in chunks)
        
        # Build section map
        section_map = {}
        for chunk in chunks:
            section = chunk.metadata.section_type.value if chunk.metadata.section_type else "unknown"
            section_map[section] = section_map.get(section, 0) + 1
        
        # Calculate statistics
        statistics = {
            "avg_tokens_per_chunk": total_tokens / len(chunks) if chunks else 0,
            "max_chunk_tokens": max(c.metadata.token_count for c in chunks) if chunks else 0,
            "min_chunk_tokens": min(c.metadata.token_count for c in chunks) if chunks else 0,
            "chunks_with_tables": sum(1 for c in chunks if c.metadata.has_tables),
            "llm_required_chunks": sum(1 for sc in super_chunks if sc.requires_llm),
            "table_only_chunks": sum(1 for sc in super_chunks if sc.table_only),
        }
        
        return ChunkingResult(
            chunks=chunks,
            super_chunks=super_chunks,
            total_tokens=total_tokens,
            total_pages=len(pages),
            section_map=section_map,
            statistics=statistics,
        )
    
    def _build_context_header(
        self,
        section_type: SectionType,
        page_number: int,
    ) -> str:
        """Build context header for chunk.
        
        Args:
            section_type: Section type
            page_number: Page number
            
        Returns:
            Context header string
        """
        section_name = section_type.value.replace("_", " ").title()
        return f"{section_name} (Page {page_number})"
    
    def _generate_stable_id(
        self,
        document_id: Optional[UUID],
        chunk_index: int,
    ) -> str:
        """Generate stable chunk ID.
        
        Args:
            document_id: Document ID
            chunk_index: Chunk index
            
        Returns:
            Stable chunk ID
        """
        doc_str = str(document_id) if document_id else "unknown"
        return f"chunk_{doc_str}_{chunk_index}"
    
    def _extract_page_number(self, docling_chunk: Any) -> int:
        """Extract page number from Docling chunk.
        
        Args:
            docling_chunk: Docling chunk object
            
        Returns:
            Page number (1-indexed)
        """
        # Try to get page number from chunk metadata
        try:
            if hasattr(docling_chunk, 'meta') and docling_chunk.meta:
                if 'page' in docling_chunk.meta:
                    return int(docling_chunk.meta['page'])
        except Exception:
            pass
        return 1
    
    def _extract_context_header(
        self,
        contextualized: str,
        original: str,
    ) -> Optional[str]:
        """Extract context header from contextualized text.
        
        Args:
            contextualized: Contextualized text from Docling
            original: Original chunk text
            
        Returns:
            Context header if found
        """
        if contextualized == original:
            return None
        
        # Context is typically prepended
        if contextualized.startswith(original):
            return None
        
        # Find where original starts
        idx = contextualized.find(original)
        if idx > 0:
            return contextualized[:idx].strip()
        
        return None
    
    def _docling_to_pages(self, docling_document: Any) -> List[PageData]:
        """Convert Docling document to PageData list.
        
        Args:
            docling_document: Docling document object
            
        Returns:
            List of PageData
        """
        try:
            markdown = docling_document.export_to_markdown(
                page_break_placeholder="\n\n<<<DOC_PAGE_BREAK>>>\n\n"
            )
            pages_text = markdown.split("<<<DOC_PAGE_BREAK>>>")
            
            pages = []
            for idx, page_text in enumerate(pages_text, start=1):
                pages.append(PageData(
                    page_number=idx,
                    text=page_text.strip(),
                    markdown=page_text.strip(),
                    metadata={"source": "docling_converted"},
                ))
            
            return pages
        except Exception as e:
            LOGGER.error(f"Failed to convert Docling document: {e}")
            return []

