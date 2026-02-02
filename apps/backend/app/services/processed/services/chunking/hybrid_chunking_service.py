"""Hybrid chunking service using Docling's HybridChunker.

This service implements section-aware + layout-aware chunking:
- Uses Docling's HybridChunker for tokenization-aware splitting
- Preserves document structure and hierarchy
- Creates semantically meaningful chunks for LLM processing
- Supports context enrichment for better embeddings
"""

import re
from typing import List, Optional, Dict, Any
from uuid import UUID

from app.models.page_analysis_models import SectionBoundary
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
    SectionType.COVERAGE_GRANT: [
        r'^\s*SECTION\s+II\s*[-–]\s*COVERED\s+AUTOS\s+LIABILITY\s+COVERAGE\s*$',
        r'^\s*PHYSICAL\s+DAMAGE\s+COVERAGE\s*$',
        r'^\s*SECTION\s+III\s*[-–]\s*PHYSICAL\s+DAMAGE\s+COVERAGE\s*$',
        r'^\s*WE\s+WILL\s+PAY\s*$',
        r'^\s*WE\s+WILL\s+ALSO\s+PAY\s*$',
    ],
    SectionType.COVERAGE_EXTENSION: [
        r'^\s*SUPPLEMENTARY\s+PAYMENTS\s*$',
        r'^\s*OUT-OF-STATE\s+COVERAGE\s+EXTENSIONS\s*$',
        r'^\s*TRANSPORTATION\s+EXPENSES\s*$',
        r'^\s*LOSS\s+OF\s+USE\s+EXPENSES\s*$',
        r'^\s*COVERAGE\s+EXTENSIONS\s*$',
    ],
    SectionType.LIMITS: [
        r'^\s*LIMIT\s+OF\s+INSURANCE\s*$',
        r'^\s*LIMITS\s+AND\s+DEDUCTIBLES\s*$',
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
    SectionType.DEFINITIONS: [
        r'^\s*DEFINITIONS?\s*$',
        r'^\s*SECTION\s+[IVX]+[\.\:]\s*DEFINITIONS?\s*$',
    ],
    SectionType.INSURED_DEFINITION: [
        r'^\s*WHO\s+IS\s+AN\s+INSURED\s*$',
    ],
    SectionType.SOV: [
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
    SectionType.VEHICLE_DETAILS: [
        r'^\s*VEHICLE\s+DETAILS?\s*$',
        r'^\s*VEHICLE\s+SCHEDULE\s*$',
        r'^\s*COVERED\s+Auto(?:s|mobile|mobiles)?\s*$',
        r'^\s*SCHEDULE\s+OF\s+COVERED\s+Auto(?:s|mobile|mobiles)?\s*$',
    ],
    SectionType.INSURED_DECLARED_VALUE: [
        r'^\s*INSURED(?:\'\s*S)?\s+DECLARED\s+VALUE\s*$',
        r'^\s*IDV\s*$',
    ],
    SectionType.LIABILITY_COVERAGES: [
        r'^\s*LIABILITY\s+COVERAGES?\s*$',
        r'^\s*LIABILITY\s+LIMITS?\s*$',
    ],
    SectionType.DRIVER_INFORMATION: [
        r'^\s*DRIVER(?:S|\s+INFORMATION)?\s*$',
        r'^\s*SCHEDULE\s+OF\s+DRIVERS?\s*$',
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
        min_tokens_per_chunk: Minimum tokens before flushing
        overlap_tokens: Token overlap between chunks
        tokenizer: Tokenizer name for HybridChunker
        token_counter: Token counting utility
        max_tokens_per_super_chunk: Maximum tokens per super-chunk (for LLM limits)
    """
    
    # Default super-chunk limits for LLM processing
    DEFAULT_MAX_TOKENS_PER_SUPER_CHUNK = 6000
    DEFAULT_MIN_TOKENS_PER_CHUNK = 300
    FALLBACK_MIN_TOKENS = 200
    
    def __init__(
        self,
        max_tokens: int = 1500,
        overlap_tokens: int = 50,
        min_tokens_per_chunk: int = DEFAULT_MIN_TOKENS_PER_CHUNK,
        tokenizer: str = "sentence-transformers/all-MiniLM-L6-v2",
        merge_peers: bool = True,
        max_tokens_per_super_chunk: int = DEFAULT_MAX_TOKENS_PER_SUPER_CHUNK,
    ):
        """Initialize hybrid chunking service.
        
        Args:
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Token overlap between chunks
            min_tokens_per_chunk: Minimum tokens before flushing a chunk (default 300)
            tokenizer: HuggingFace tokenizer name for HybridChunker
            merge_peers: Whether to merge small sibling chunks
            max_tokens_per_super_chunk: Maximum tokens per super-chunk for LLM calls
        """
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        # Enforce minimum of FALLBACK_MIN_TOKENS (200) even if lower value provided
        self.min_tokens_per_chunk = max(min_tokens_per_chunk, self.FALLBACK_MIN_TOKENS)
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
                "min_tokens_per_chunk": self.min_tokens_per_chunk,
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
        section_boundaries: Optional[List[SectionBoundary]] = None,
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
                "has_section_boundaries": section_boundaries is not None,
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
        chunks = self._create_hybrid_chunks(
            pages, 
            page_sections, 
            document_id,
            section_boundaries=section_boundaries
        )
        
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
        (e.g., "endorsements", "sov").
        
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
            # Handle comma-separated section types (take the first one as primary)
            if isinstance(section_str, str) and "," in section_str:
                primary_section_str = section_str.split(",")[0]
                LOGGER.debug(f"Handling multi-section page {page_num}: '{section_str}' -> using primary '{primary_section_str}'")
                section_str = primary_section_str

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
        
        Optimized for paragraph-level header detection.
        
        Args:
            text: Text content to analyze
            
        Returns:
            Detected SectionType
        """
        if not text:
            return SectionType.UNKNOWN
        
        # Check first few lines for section headers
        # Headers are typically short and at the beginning of a paragraph
        lines = text.split('\n')[:3]
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) > 200:
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
        section_boundaries: Optional[List[SectionBoundary]] = None,
    ) -> List[HybridChunk]:
        """Create hybrid chunks from pages with semantic section awareness.
        
        This implementation processes the document as a stream of paragraphs,
        detecting section transitions within pages and preserving context.
        
        Args:
            pages: List of pages
            page_sections: Initial mapping of page numbers to sections (baselines)
            document_id: Document ID for metadata
            section_boundaries: Optional intra-page section boundaries
            
        Returns:
            List of HybridChunks
        """
        from app.utils.section_type_mapper import SectionTypeMapper
        
        chunks = []
        chunk_index = 0
        
        current_section = SectionType.UNKNOWN
        current_subsection: Optional[str] = None
        current_buffer = []
        current_tokens = 0
        current_page_range = set()
        
        # Semantic state
        current_semantic_role: Optional[str] = None
        current_coverage_effects: List[str] = []
        current_exclusion_effects: List[str] = []
        
        # State tracking for current chunk
        current_has_tables = False
        current_table_count = 0
        
        # Index boundaries by page for fast lookup
        # Also create a map of page -> covering boundary for continuation page support
        boundaries_by_page = {}
        boundaries_covering_page = {}  # Maps page number -> boundary that covers it
        if section_boundaries:
            LOGGER.info(
                f"Processing {len(section_boundaries)} section boundaries for semantic metadata",
                extra={
                    "boundaries_with_semantic_role": sum(1 for b in section_boundaries if b.semantic_role),
                    "boundaries_with_coverage_effects": sum(1 for b in section_boundaries if b.coverage_effects),
                    "boundaries_with_exclusion_effects": sum(1 for b in section_boundaries if b.exclusion_effects),
                }
            )
            for b in section_boundaries:
                if b.start_page not in boundaries_by_page:
                    boundaries_by_page[b.start_page] = []
                boundaries_by_page[b.start_page].append(b)

                # Map all pages in this boundary's range to the boundary
                # This enables semantic_role inheritance for continuation pages
                for page_in_range in range(b.start_page, b.end_page + 1):
                    # Only set if not already set (prefer boundary that starts on this page)
                    if page_in_range not in boundaries_covering_page:
                        boundaries_covering_page[page_in_range] = b

                # Debug log for boundaries with semantic metadata
                if b.semantic_role or b.coverage_effects or b.exclusion_effects:
                    role_val = b.semantic_role.value if hasattr(b.semantic_role, 'value') else b.semantic_role
                    LOGGER.debug(
                        f"Boundary pages {b.start_page}-{b.end_page}: "
                        f"semantic_role={role_val}, "
                        f"effective_section_type={b.effective_section_type}, "
                        f"coverage_effects={b.coverage_effects}, "
                        f"exclusion_effects={b.exclusion_effects}"
                    )

        for page in pages:
            page_num = page.page_number
            content = page.get_content()
            paragraphs = self._split_by_paragraphs(content)
            
            # Baseline section from manifest/OCR metadata for this page
            manifest_section = page_sections.get(page_num, SectionType.UNKNOWN)
            
            # Page-level table info
            page_has_tables = page.metadata.get("has_tables", False)
            page_table_count = page.metadata.get("table_count", 0)
            
            # Line tracking for boundaries (very simplified, assumes 1 para = few lines)
            # This is a bit of a heuristic since we've split by paragraphs not lines
            # but usually paragraph transitions align with section transitions.
            current_line_estimation = 1
            
            for para_idx, para in enumerate(paragraphs):
                para_tokens = self.token_counter.count_tokens(para)
                para_line_count = para.count('\n') + 1
                
                # Detect section transition
                detected_section = self._detect_section_type(para)
                
                transition_occurred = False
                new_section = current_section
                new_subsection = current_subsection
                new_semantic_role = current_semantic_role
                new_coverage_effects = current_coverage_effects
                new_exclusion_effects = current_exclusion_effects

                # Check for explicit boundary transition
                page_boundaries = boundaries_by_page.get(page_num, [])
                boundary_section = SectionType.UNKNOWN
                current_boundary = None

                for b in page_boundaries:
                    # Case 1: Page-level boundary (apply to first paragraph)
                    if b.start_line is None and para_idx == 0:
                        boundary_section = SectionTypeMapper.page_type_to_section_type(b.section_type)
                        current_boundary = b
                    # Case 2: Specific line boundary
                    elif b.start_line is not None:
                        if current_line_estimation >= b.start_line:
                            boundary_section = SectionTypeMapper.page_type_to_section_type(b.section_type)
                            current_boundary = b

                # Log when we match a boundary with semantic info
                if current_boundary and para_idx == 0:
                    role_val = current_boundary.semantic_role
                    role_str = role_val.value if hasattr(role_val, 'value') else role_val
                    LOGGER.info(
                        f"Matched boundary on page {page_num}: section={boundary_section.value}, "
                        f"semantic_role={role_str}, coverage_effects={current_boundary.coverage_effects}, "
                        f"exclusion_effects={current_boundary.exclusion_effects}"
                    )

                # CONTINUATION PAGE SUPPORT: If no boundary starts on this page but
                # this page is covered by an existing boundary, inherit semantic context
                # This ensures multi-page endorsements maintain their semantic_role
                covering_boundary = boundaries_covering_page.get(page_num)
                if covering_boundary and not current_boundary and para_idx == 0:
                    # This is a continuation page - inherit semantic context from covering boundary
                    # Since this is not a "transition" (same section), we update current state directly
                    if covering_boundary.semantic_role:
                        role = covering_boundary.semantic_role
                        inherited_role = role.value if hasattr(role, 'value') else role
                        # Update both new_ and current_ to ensure proper propagation
                        new_semantic_role = inherited_role
                        current_semantic_role = inherited_role
                        LOGGER.debug(
                            f"Inheriting semantic_role '{inherited_role}' from covering boundary "
                            f"(pages {covering_boundary.start_page}-{covering_boundary.end_page}) for continuation page {page_num}"
                        )
                    if covering_boundary.coverage_effects:
                        inherited_cov_effects = [e.value if hasattr(e, 'value') else e for e in covering_boundary.coverage_effects]
                        new_coverage_effects = inherited_cov_effects
                        current_coverage_effects = inherited_cov_effects
                    if covering_boundary.exclusion_effects:
                        inherited_excl_effects = [e.value if hasattr(e, 'value') else e for e in covering_boundary.exclusion_effects]
                        new_exclusion_effects = inherited_excl_effects
                        current_exclusion_effects = inherited_excl_effects

                # Capture effective section type from boundary if available
                boundary_effective_type = None
                if current_boundary and hasattr(current_boundary, 'effective_section_type') and current_boundary.effective_section_type:
                    boundary_effective_type = SectionTypeMapper.page_type_to_section_type(current_boundary.effective_section_type)

                
                # Priority: 1. Detected from text, 2. Explicit Boundary, 3. Manifest page-level
                if detected_section != SectionType.UNKNOWN and detected_section != current_section:
                    LOGGER.info(
                        f"Section transition detected via header: {current_section} -> {detected_section}",
                        extra={"page": page_num, "para_idx": para_idx}
                    )
                    transition_occurred = True
                    new_section = detected_section
                    
                    # Normalize detected section to core/subsection
                    core = SectionTypeMapper.normalize_to_core_section(detected_section)
                    if core != detected_section:
                        new_section = core
                        new_subsection = detected_section.value
                        LOGGER.info(f"Normalized detected section: {detected_section} -> {core}({new_subsection})")
                if boundary_section != SectionType.UNKNOWN:
                    # Check for subsection transition or section transition
                    
                    # If detected boundary section is different OR subsection is different
                    new_subsection = current_boundary.sub_section_type if current_boundary else None
                    
                    # Update semantic info from boundary if it exists
                    if current_boundary:
                        role = current_boundary.semantic_role
                        new_semantic_role = role.value if role and hasattr(role, 'value') else role
                        new_coverage_effects = [e.value if hasattr(e, 'value') else e for e in (current_boundary.coverage_effects or [])]
                        new_exclusion_effects = [e.value if hasattr(e, 'value') else e for e in (current_boundary.exclusion_effects or [])]

                    # HARD STOP: If boundary section matches one of our critical ISO anchors, we MUST flush
                    ISO_HARD_STOPS = {
                        SectionType.COVERAGE_GRANT,
                        SectionType.INSURED_DEFINITION,
                        SectionType.LIMITS,
                        SectionType.EXCLUSIONS,
                        SectionType.CONDITIONS,
                        SectionType.DEFINITIONS
                    }
                    
                    if boundary_section != current_section or new_subsection != current_subsection or new_semantic_role != current_semantic_role or boundary_section in ISO_HARD_STOPS:
                        LOGGER.info(
                            f"Section transition via boundary: {current_section} -> {boundary_section}, "
                            f"new_semantic_role={new_semantic_role}",
                            extra={"page": page_num, "line": current_line_estimation, "anchor": current_boundary.anchor_text}
                        )
                        transition_occurred = True
                        new_section = boundary_section
                elif para_idx == 0 and manifest_section != SectionType.UNKNOWN and manifest_section != current_section:
                    
                    actual_manifest_section = manifest_section
                    if isinstance(manifest_section, str) and "," in manifest_section:
                        first_type = manifest_section.split(",")[0]
                        actual_manifest_section = SectionTypeMapper.string_to_section_type(first_type)

                    if actual_manifest_section != current_section:
                        LOGGER.info(
                            f"Section transition detected via manifest: {current_section} -> {actual_manifest_section}",
                            extra={"page": page_num}
                        )
                        transition_occurred = True
                        new_section = actual_manifest_section
                
                # ACORD Certificate Guard: Hard-block semantic interpretation on certificates
                if new_section == SectionType.CERTIFICATE_OF_INSURANCE:
                    new_semantic_role = None
                    new_coverage_effects = []
                    new_exclusion_effects = []

                # Handle oversized paragraph - split it internally
                if para_tokens > self.max_tokens:
                    if current_buffer:
                        chunks.append(self._flush_chunk(
                            buffer=current_buffer,
                            section_type=current_section,
                            effective_section_type=current_section, # Default
                            original_section_type=current_section,
                            subsection_type=current_subsection,
                            page_range=current_page_range,
                            document_id=document_id,
                            chunk_index=chunk_index,
                            tokens=current_tokens,
                            has_tables=current_has_tables,
                            table_count=current_table_count,
                            semantic_role=current_semantic_role,
                            coverage_effects=current_coverage_effects,
                            exclusion_effects=current_exclusion_effects,
                        ))
                        chunk_index += 1
                        current_buffer = []
                        current_tokens = 0
                        current_page_range = {page_num}
                        current_has_tables = False
                        current_table_count = 0
                    
                    # Update section if it was detected in this large paragraph
                    if transition_occurred:
                        current_section = new_section
                        current_subsection = new_subsection
                        current_semantic_role = new_semantic_role
                        current_coverage_effects = new_coverage_effects
                        current_exclusion_effects = new_exclusion_effects
                    
                    # Split the paragraph
                    sub_paras = self.token_counter.split_by_token_limit(
                        para, self.max_tokens, self.overlap_tokens
                    )
                    
                    for sub_para in sub_paras[:-1]:
                        sub_tokens = self.token_counter.count_tokens(sub_para)
                        chunks.append(self._flush_chunk(
                            buffer=[sub_para],
                            section_type=current_section,
                            effective_section_type=current_section, # Default
                            original_section_type=current_section,
                            subsection_type=current_subsection,
                            page_range={page_num},
                            document_id=document_id,
                            chunk_index=chunk_index,
                            tokens=sub_tokens,
                            has_tables=page_has_tables,
                            table_count=page_table_count,
                            semantic_role=current_semantic_role,
                            coverage_effects=current_coverage_effects,
                            exclusion_effects=current_exclusion_effects,
                        ))
                        chunk_index += 1
                    
                    # Last sub-paragraph remains in buffer
                    last_para = sub_paras[-1]
                    current_buffer = [last_para]
                    current_tokens = self.token_counter.count_tokens(last_para)
                    current_page_range = {page_num}
                    current_has_tables = page_has_tables
                    current_table_count = page_table_count
                    continue

                # Determine if we should flush the current chunk
                # Flush if:
                # 1. Section transition (always flush on section change)
                # 2. Token limit reached AND minimum tokens met (prevents undersized chunks)
                token_limit_reached = current_tokens + para_tokens > self.max_tokens
                min_tokens_met = current_tokens >= self.min_tokens_per_chunk
                
                should_flush = current_buffer and (
                    transition_occurred or 
                    (token_limit_reached and min_tokens_met)
                )
                
                # Table Rule: If chunk has high table density and mentions symbols, force coverages_context
                # Heuristic: 60% of paragraphs start with table-like patterns (pipe, etc.) or page metadata says so
                if current_buffer and current_section in {SectionType.COVERAGES, SectionType.UNKNOWN}:
                    para_joined = "\n".join(current_buffer).lower()
                    if "symbol" in para_joined or "designation" in para_joined:
                        table_para_count = sum(1 for p in current_buffer if p.strip().startswith('|') or p.strip().count('|') > 2)
                        if (table_para_count / len(current_buffer) >= 0.6) or (current_has_tables and "symbol" in para_joined):
                            LOGGER.info(f"Applying symbol-table rule for page {page_num}: forcing coverages_context")
                            current_section = SectionType.COVERAGES_CONTEXT
                            current_semantic_role = None # Symbols aren't semantic modifiers
                
                if should_flush:
                    # Determine effective section types (may return multiple for dual emission)
                    effective_types = self._get_effective_section_types(
                        current_section,
                        current_semantic_role
                    )

                    # Log chunk creation with semantic info (especially for endorsements)
                    if current_section == SectionType.ENDORSEMENTS:
                        LOGGER.info(
                            f"Flushing endorsement chunk: pages={sorted(current_page_range)}, "
                            f"semantic_role={current_semantic_role}, effective_types={[t.value for t in effective_types]}"
                        )

                    for eff_type in effective_types:
                        # Create and store the chunk
                        chunk = self._flush_chunk(
                            buffer=current_buffer,
                            section_type=current_section,
                            effective_section_type=eff_type,
                            original_section_type=current_section,
                            subsection_type=current_subsection,
                            page_range=current_page_range,
                            document_id=document_id,
                            chunk_index=chunk_index,
                            tokens=current_tokens,
                            has_tables=current_has_tables,
                            table_count=current_table_count,
                            semantic_role=current_semantic_role,
                            coverage_effects=current_coverage_effects,
                            exclusion_effects=current_exclusion_effects,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                    
                    # Prepare for next chunk
                    if transition_occurred:
                        # Clear buffer on section transition
                        current_buffer = []
                        current_tokens = 0
                        current_page_range = {page_num}
                    else:
                        # Token limit reached: use overlap from current buffer
                        overlap_text = self._get_overlap_text("\n\n".join(current_buffer))
                        if overlap_text:
                            current_buffer = [overlap_text.strip()]
                            current_tokens = self.token_counter.count_tokens(overlap_text)
                        else:
                            current_buffer = []
                            current_tokens = 0
                        current_page_range = {page_num}
                    
                    current_has_tables = False
                    current_table_count = 0
                
                # Update current state
                if transition_occurred:
                    current_section = new_section
                    current_subsection = new_subsection
                    current_semantic_role = new_semantic_role
                    current_coverage_effects = new_coverage_effects
                    current_exclusion_effects = new_exclusion_effects

                # Derive semantic role from granular section types if not explicitly set by boundary
                from app.models.page_analysis_models import SemanticRole
                if current_semantic_role in {None, SemanticRole.UNKNOWN, "unknown"}:
                    if current_section == SectionType.COVERAGE_GRANT:
                        current_semantic_role = SemanticRole.COVERAGE_GRANT
                    elif current_section == SectionType.COVERAGE_EXTENSION:
                        current_semantic_role = SemanticRole.COVERAGE_EXTENSION
                    elif current_section == SectionType.LIMITS:
                        current_semantic_role = SemanticRole.LIMITS
                    elif current_section == SectionType.INSURED_DEFINITION:
                        current_semantic_role = SemanticRole.INSURED_DEFINITION
                    elif current_section == SectionType.DEFINITIONS:
                        current_semantic_role = SemanticRole.DEFINITIONS
                
                current_buffer.append(para)
                current_tokens += para_tokens
                current_page_range.add(page_num)
                if page_has_tables:
                    current_has_tables = True
                    current_table_count = max(current_table_count, page_table_count)
                
                current_line_estimation += para_line_count + 1
        
        # Flush final chunk
        if current_buffer:
            effective_types = self._get_effective_section_types(
                current_section, 
                current_semantic_role
            )
            for eff_type in effective_types:
                chunk = self._flush_chunk(
                    buffer=current_buffer,
                    section_type=current_section,
                    effective_section_type=eff_type,
                    original_section_type=current_section,
                    subsection_type=current_subsection,
                    page_range=current_page_range,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    tokens=current_tokens,
                    has_tables=current_has_tables,
                    table_count=current_table_count,
                    semantic_role=current_semantic_role,
                    coverage_effects=current_coverage_effects,
                    exclusion_effects=current_exclusion_effects,
                )
                chunks.append(chunk)
                chunk_index += 1
        
        # Post-process: merge consecutive small chunks of same section type
        # This handles cases where section boundaries created undersized chunks
        merged_chunks = self._merge_small_chunks(chunks)
        
        LOGGER.info(
            f"Chunk post-processing: {len(chunks)} -> {len(merged_chunks)} chunks after merging",
            extra={"original": len(chunks), "merged": len(merged_chunks)}
        )
            
        return merged_chunks

    def _get_effective_section_types(
        self, 
        section_type: SectionType, 
        semantic_role: Optional[str]
    ) -> List[SectionType]:
        """Resolve structural section to one or more effective extraction sections.
        
        This implements the "Semantic Projection" logic where endorsements 
        become virtual coverage/exclusion sections.
        """
        # Use string comparison to be safe with enums vs strings
        role_val = semantic_role.value if hasattr(semantic_role, 'value') else str(semantic_role) if semantic_role else None

        from app.models.page_analysis_models import SemanticRole

        # 1. Dual Emission (BOTH) takes highest priority for any section
        # Compare to .value since role_val is a string
        if role_val == SemanticRole.BOTH.value:
            return [SectionType.COVERAGES, SectionType.EXCLUSIONS]

        # 2. Endorsement Semantic Projection
        if section_type == SectionType.ENDORSEMENTS and role_val:
            if role_val == SemanticRole.COVERAGE_MODIFIER.value:
                return [SectionType.COVERAGES]
            elif role_val == SemanticRole.EXCLUSION_MODIFIER.value:
                return [SectionType.EXCLUSIONS]
            elif role_val == SemanticRole.ADMINISTRATIVE_ONLY.value:
                return [SectionType.ENDORSEMENTS]
                
        # 3. Base Policy Sections are authoritative
        if section_type in {
            SectionType.COVERAGES, 
            SectionType.EXCLUSIONS, 
            SectionType.CONDITIONS, 
            SectionType.DEFINITIONS,
            SectionType.DECLARATIONS
        }:
            return [SectionType(section_type)]

        # 4. Default: Use structural section
        return [section_type]

    def _flush_chunk(
        self,
        buffer: List[str],
        section_type: SectionType,
        effective_section_type: Optional[SectionType],
        original_section_type: Optional[SectionType],
        subsection_type: Optional[str],
        page_range: set,
        document_id: Optional[UUID],
        chunk_index: int,
        tokens: int,
        has_tables: bool,
        table_count: int,
        semantic_role: Optional[str] = None,
        coverage_effects: List[str] = None,
        exclusion_effects: List[str] = None,
    ) -> HybridChunk:
        """Create a HybridChunk from the current buffer and state."""
        content = "\n\n".join(buffer).strip()
        sorted_pages = sorted(list(page_range))
        primary_page = sorted_pages[0] if sorted_pages else 1
        
        # Determine chunk role
        if has_tables and table_count > 0:
            chunk_role = ChunkRole.TABLE if table_count > 2 else ChunkRole.MIXED
        else:
            chunk_role = ChunkRole.TEXT
            
        # Get document role from config
        from app.services.processed.services.chunking.hybrid_models import SECTION_CONFIG
        config = SECTION_CONFIG.get(section_type, {})
        is_non_contractual = config.get("is_non_contractual", False)
        document_role = "non_contractual" if is_non_contractual else "contractual"

        metadata = HybridChunkMetadata(
            document_id=document_id,
            page_number=primary_page,
            page_range=sorted_pages,
            section_type=section_type,
            section_name=section_type.value.replace("_", " ").title(),
            subsection_type=subsection_type,
            chunk_index=chunk_index,
            token_count=tokens,
            stable_chunk_id=self._generate_stable_id(document_id, chunk_index),
            chunk_role=chunk_role,
            has_tables=has_tables,
            table_count=table_count,
            context_header=self._build_context_header(section_type, primary_page),
            source="semantic_paragraph_chunker",
            semantic_role=semantic_role,
            coverage_effects=coverage_effects or [],
            exclusion_effects=exclusion_effects or [],
            original_section_type=original_section_type,
            effective_section_type=effective_section_type,
            document_role=document_role,
        )
        
        # Enrich metadata with original section if it was projected
        if effective_section_type and effective_section_type != section_type:
            if not metadata.subsection_type:
                metadata.subsection_type = f"projected_from_{section_type.value}"
        if original_section_type and original_section_type != section_type:
            metadata.subsection_type = f"projected_from_{original_section_type.value}"

        return HybridChunk(
            text=content,
            contextualized_text=f"{metadata.context_header}\n\n{content}" if metadata.context_header else content,
            metadata=metadata,
        )
    
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
    
    def _merge_small_chunks(
        self,
        chunks: List[HybridChunk],
    ) -> List[HybridChunk]:
        """Merge consecutive small chunks with same section type and semantic intent.
        
        This method merges undersized chunks (<min_tokens_per_chunk) with their
        neighbors when they share the same effective section type AND semantic role.
        Merging is allowed across page boundaries per user requirement.
        
        Args:
            chunks: List of hybrid chunks to potentially merge
            
        Returns:
            List of merged chunks (fewer, larger chunks)
        """
        if not chunks or len(chunks) < 2:
            return chunks
        
        merged = []
        current = chunks[0]
        
        for next_chunk in chunks[1:]:
            # Check if chunks can be merged:
            # 1. Same effective section type AND same structural section type
            # 2. Same semantic role (or both None)
            # 3. Current chunk is below min_tokens threshold
            same_section = (
                current.metadata.section_type == next_chunk.metadata.section_type and
                current.metadata.effective_section_type == next_chunk.metadata.effective_section_type
            )
            same_semantic = (
                current.metadata.semantic_role == next_chunk.metadata.semantic_role
            )
            current_undersized = current.metadata.token_count < self.min_tokens_per_chunk
            combined_fits = (
                current.metadata.token_count + next_chunk.metadata.token_count 
                <= self.max_tokens
            )
            
            if same_section and same_semantic and current_undersized and combined_fits:
                # Merge next_chunk into current
                merged_text = current.text + "\n\n" + next_chunk.text
                merged_tokens = current.metadata.token_count + next_chunk.metadata.token_count
                
                # Combine page ranges
                merged_page_range = list(set(
                    (current.metadata.page_range or [current.metadata.page_number]) +
                    (next_chunk.metadata.page_range or [next_chunk.metadata.page_number])
                ))
                merged_page_range.sort()
                
                # Create merged metadata
                merged_metadata = HybridChunkMetadata(
                    document_id=current.metadata.document_id,
                    page_number=merged_page_range[0],
                    page_range=merged_page_range,
                    section_type=current.metadata.section_type,
                    section_name=current.metadata.section_name,
                    subsection_type=current.metadata.subsection_type,
                    chunk_index=current.metadata.chunk_index,
                    token_count=merged_tokens,
                    stable_chunk_id=current.metadata.stable_chunk_id,
                    chunk_role=current.metadata.chunk_role,
                    has_tables=current.metadata.has_tables or next_chunk.metadata.has_tables,
                    table_count=max(current.metadata.table_count or 0, next_chunk.metadata.table_count or 0),
                    context_header=current.metadata.context_header,
                    source="merged_semantic_paragraph_chunker",
                    semantic_role=current.metadata.semantic_role,
                    coverage_effects=list(set(
                        (current.metadata.coverage_effects or []) + 
                        (next_chunk.metadata.coverage_effects or [])
                    )),
                    exclusion_effects=list(set(
                        (current.metadata.exclusion_effects or []) + 
                        (next_chunk.metadata.exclusion_effects or [])
                    )),
                    original_section_type=current.metadata.original_section_type,
                    effective_section_type=current.metadata.effective_section_type,
                    document_role=current.metadata.document_role,
                )
                
                current = HybridChunk(
                    text=merged_text,
                    contextualized_text=f"{merged_metadata.context_header}\n\n{merged_text}" if merged_metadata.context_header else merged_text,
                    metadata=merged_metadata,
                )
                
                LOGGER.debug(
                    f"Merged chunk: {merged_tokens} tokens, pages {merged_page_range}",
                    extra={"section": current.metadata.section_type.value}
                )
            else:
                # Cannot merge, finalize current and start new
                merged.append(current)
                current = next_chunk
        
        # Don't forget the last chunk
        merged.append(current)
        
        return merged
    
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
        
        # Build section map using structural section type
        section_map = {}
        for chunk in chunks:
            # Use original/structural section for stats
            section = (
                chunk.metadata.original_section_type.value 
                if chunk.metadata.original_section_type 
                else chunk.metadata.section_type.value 
                if chunk.metadata.section_type 
                else "unknown"
            )
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

