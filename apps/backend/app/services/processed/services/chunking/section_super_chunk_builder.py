"""Section super-chunk builder for extraction pipeline.

This module provides utilities for building and managing section super-chunks,
which aggregate related chunks for batch LLM processing.
"""

from typing import List, Dict, Optional, Tuple, Any
from uuid import UUID
from dataclasses import dataclass, field

from app.services.processed.services.chunking.hybrid_models import (
    HybridChunk,
    SectionType,
    SectionSuperChunk,
    ChunkingResult,
    SECTION_CONFIG,
)
from app.services.processed.services.chunking.token_counter import TokenCounter
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class SuperChunkBatch:
    """Represents a batch of super-chunks for LLM processing.
    
    Batches are optimized for efficient LLM API calls while respecting
    token limits and section boundaries.
    
    Attributes:
        super_chunks: List of super-chunks in this batch
        total_tokens: Total tokens in the batch
        batch_index: Index of this batch
        section_types: Section types included in batch
    """
    
    super_chunks: List[SectionSuperChunk] = field(default_factory=list)
    total_tokens: int = 0
    batch_index: int = 0
    section_types: List[str] = field(default_factory=list)
    
    def add_super_chunk(self, super_chunk: SectionSuperChunk) -> None:
        """Add a super-chunk to the batch."""
        self.super_chunks.append(super_chunk)
        self.total_tokens += super_chunk.total_tokens
        if super_chunk.section_type.value not in self.section_types:
            self.section_types.append(super_chunk.section_type.value)


class SectionSuperChunkBuilder:
    """Builder for creating and managing section super-chunks.
    
    This builder implements the section grouping strategy:
    - Groups chunks by semantic section
    - Respects section-specific token limits
    - Creates optimized batches for LLM processing
    - Handles section merging and splitting
    
    Attributes:
        max_tokens_per_super_chunk: Maximum tokens per super-chunk
        max_tokens_per_batch: Maximum tokens per LLM batch
        token_counter: Token counting utility
    """
    
    # Default limits
    DEFAULT_MAX_TOKENS_PER_SUPER_CHUNK = 8000
    DEFAULT_MAX_TOKENS_PER_BATCH = 12000
    
    def __init__(
        self,
        max_tokens_per_super_chunk: int = DEFAULT_MAX_TOKENS_PER_SUPER_CHUNK,
        max_tokens_per_batch: int = DEFAULT_MAX_TOKENS_PER_BATCH,
    ):
        """Initialize super-chunk builder.
        
        Args:
            max_tokens_per_super_chunk: Maximum tokens per super-chunk
            max_tokens_per_batch: Maximum tokens per LLM batch
        """
        self.max_tokens_per_super_chunk = max_tokens_per_super_chunk
        self.max_tokens_per_batch = max_tokens_per_batch
        self.token_counter = TokenCounter()
        
        LOGGER.info(
            "Initialized SectionSuperChunkBuilder",
            extra={
                "max_tokens_per_super_chunk": max_tokens_per_super_chunk,
                "max_tokens_per_batch": max_tokens_per_batch,
            }
        )
    
    def build_super_chunks(
        self,
        chunks: List[HybridChunk],
        document_id: Optional[UUID] = None,
    ) -> List[SectionSuperChunk]:
        """Build section super-chunks from hybrid chunks.
        
        This method groups chunks by section type and creates super-chunks
        optimized for LLM processing.
        
        Args:
            chunks: List of hybrid chunks
            document_id: Optional document ID
            
        Returns:
            List of SectionSuperChunks sorted by processing priority
        """
        if not chunks:
            return []
        
        LOGGER.info(
            "Building super-chunks",
            extra={
                "document_id": str(document_id) if document_id else None,
                "chunk_count": len(chunks),
            }
        )
        
        # Group chunks by section type
        section_groups = self._group_by_section(chunks)
        
        # Create super-chunks for each section
        super_chunks = []
        for section_type, section_chunks in section_groups.items():
            section_super_chunks = self._create_section_super_chunks(
                section_type=section_type,
                chunks=section_chunks,
                document_id=document_id,
            )
            super_chunks.extend(section_super_chunks)
        
        # Sort by processing priority
        super_chunks.sort(key=lambda sc: sc.processing_priority)
        
        LOGGER.info(
            "Super-chunks built",
            extra={
                "document_id": str(document_id) if document_id else None,
                "super_chunk_count": len(super_chunks),
                "sections": [sc.section_type.value for sc in super_chunks],
            }
        )
        
        return super_chunks
    
    def _group_by_section(
        self,
        chunks: List[HybridChunk],
    ) -> Dict[SectionType, List[HybridChunk]]:
        """Group chunks by section type.
        
        Args:
            chunks: List of hybrid chunks
            
        Returns:
            Dict mapping section types to chunk lists
        """
        groups: Dict[SectionType, List[HybridChunk]] = {}
        
        for chunk in chunks:
            # Use effective type for LLM routing, fall back to structural
            section_type = (
                chunk.metadata.effective_section_type or 
                chunk.metadata.section_type or 
                SectionType.UNKNOWN
            )
            if section_type not in groups:
                groups[section_type] = []
            groups[section_type].append(chunk)
        
        return groups
    
    def _create_section_super_chunks(
        self,
        section_type: SectionType,
        chunks: List[HybridChunk],
        document_id: Optional[UUID],
    ) -> List[SectionSuperChunk]:
        """Create super-chunks for a specific section.
        
        Handles splitting large sections into multiple super-chunks
        while respecting token limits. Uses section-specific max_tokens
        if available, otherwise falls back to global max_tokens_per_super_chunk.
        
        Args:
            section_type: Section type
            chunks: Chunks for this section
            document_id: Document ID
            
        Returns:
            List of super-chunks for this section
        """
        config = SECTION_CONFIG.get(section_type, SECTION_CONFIG[SectionType.UNKNOWN])
        max_chunks = config["max_chunks"]
        
        # Use section-specific max_tokens if available, else global limit
        section_max_tokens = config.get("max_tokens", self.max_tokens_per_super_chunk)
        effective_max_tokens = min(section_max_tokens, self.max_tokens_per_super_chunk)
        
        # Calculate total tokens
        total_tokens = sum(c.metadata.token_count for c in chunks)
        
        LOGGER.debug(
            f"Creating super-chunks for section {section_type.value}",
            extra={
                "section_type": section_type.value,
                "chunk_count": len(chunks),
                "total_tokens": total_tokens,
                "effective_max_tokens": effective_max_tokens,
                "max_chunks_per_super": max_chunks,
            }
        )
        
        # If within limits, create single super-chunk
        if total_tokens <= effective_max_tokens and len(chunks) <= max_chunks:
            super_chunk = self._create_super_chunk(
                section_type=section_type,
                chunks=chunks,
                document_id=document_id,
                part_index=0,
            )
            return [super_chunk]
        
        # Split into multiple super-chunks
        return self._split_into_super_chunks(
            section_type=section_type,
            chunks=chunks,
            document_id=document_id,
            max_chunks_per_super=max_chunks,
            max_tokens_per_super=effective_max_tokens,
        )
    
    def _split_into_super_chunks(
        self,
        section_type: SectionType,
        chunks: List[HybridChunk],
        document_id: Optional[UUID],
        max_chunks_per_super: int,
        max_tokens_per_super: Optional[int] = None,
    ) -> List[SectionSuperChunk]:
        """Split large section into multiple super-chunks.
        
        Args:
            section_type: Section type
            chunks: All chunks for section
            document_id: Document ID
            max_chunks_per_super: Maximum chunks per super-chunk
            max_tokens_per_super: Maximum tokens per super-chunk (uses global if None)
            
        Returns:
            List of super-chunks
        """
        effective_max_tokens = max_tokens_per_super or self.max_tokens_per_super_chunk
        
        super_chunks = []
        current_chunks: List[HybridChunk] = []
        current_tokens = 0
        part_index = 0
        
        for chunk in chunks:
            chunk_tokens = chunk.metadata.token_count
            
            # Check if adding this chunk would exceed limits
            would_exceed_tokens = current_tokens + chunk_tokens > effective_max_tokens
            would_exceed_count = len(current_chunks) >= max_chunks_per_super
            
            if current_chunks and (would_exceed_tokens or would_exceed_count):
                # Save current super-chunk
                super_chunk = self._create_super_chunk(
                    section_type=section_type,
                    chunks=current_chunks,
                    document_id=document_id,
                    part_index=part_index,
                )
                super_chunks.append(super_chunk)
                
                LOGGER.debug(
                    f"Created super-chunk part {part_index + 1} for {section_type.value}",
                    extra={
                        "section_type": section_type.value,
                        "part_index": part_index,
                        "chunk_count": len(current_chunks),
                        "tokens": current_tokens,
                    }
                )
                
                # Start new super-chunk
                current_chunks = [chunk]
                current_tokens = chunk_tokens
                part_index += 1
            else:
                current_chunks.append(chunk)
                current_tokens += chunk_tokens
        
        # Save final super-chunk
        if current_chunks:
            super_chunk = self._create_super_chunk(
                section_type=section_type,
                chunks=current_chunks,
                document_id=document_id,
                part_index=part_index,
            )
            super_chunks.append(super_chunk)
            
            LOGGER.debug(
                f"Created final super-chunk part {part_index + 1} for {section_type.value}",
                extra={
                    "section_type": section_type.value,
                    "part_index": part_index,
                    "chunk_count": len(current_chunks),
                    "tokens": current_tokens,
                }
            )
        
        LOGGER.info(
            f"Split section {section_type.value} into {len(super_chunks)} super-chunks",
            extra={
                "section_type": section_type.value,
                "super_chunk_count": len(super_chunks),
                "total_chunks": len(chunks),
                "max_tokens_per_super": effective_max_tokens,
            }
        )
        
        return super_chunks
    
    def _create_super_chunk(
        self,
        section_type: SectionType,
        chunks: List[HybridChunk],
        document_id: Optional[UUID],
        part_index: int,
    ) -> SectionSuperChunk:
        """Create a single super-chunk.
        
        Args:
            section_type: Section type
            chunks: Chunks for this super-chunk
            document_id: Document ID
            part_index: Part index for multi-part sections
            
        Returns:
            SectionSuperChunk
        """
        config = SECTION_CONFIG.get(section_type, SECTION_CONFIG[SectionType.UNKNOWN])
        
        section_name = section_type.value.replace("_", " ").title()
        if part_index > 0:
            section_name = f"{section_name} (Part {part_index + 1})"
        
        super_chunk_id = None
        if document_id:
            super_chunk_id = f"sc_{str(document_id)}_{section_type.value}_{part_index}"
        
        return SectionSuperChunk(
            section_type=section_type,
            section_name=section_name,
            chunks=chunks,
            document_id=document_id,
            super_chunk_id=super_chunk_id,
            processing_priority=config["priority"],
            requires_llm=config["requires_llm"],
            table_only=config["table_only"],
        )
    
    def create_processing_batches(
        self,
        super_chunks: List[SectionSuperChunk],
        batch_by_section: bool = True,
    ) -> List[SuperChunkBatch]:
        """Create optimized batches for LLM processing.
        
        This method groups super-chunks into batches that respect token limits
        while maximizing efficiency.
        
        Args:
            super_chunks: List of super-chunks to batch
            batch_by_section: Whether to keep sections together in batches
            
        Returns:
            List of processing batches
        """
        if not super_chunks:
            return []
        
        # Filter to LLM-required super-chunks
        llm_super_chunks = [sc for sc in super_chunks if sc.requires_llm]
        
        if not llm_super_chunks:
            return []
        
        LOGGER.info(
            "Creating processing batches",
            extra={
                "super_chunk_count": len(llm_super_chunks),
                "batch_by_section": batch_by_section,
            }
        )
        
        if batch_by_section:
            return self._batch_by_section(llm_super_chunks)
        else:
            return self._batch_by_tokens(llm_super_chunks)
    
    def _batch_by_section(
        self,
        super_chunks: List[SectionSuperChunk],
    ) -> List[SuperChunkBatch]:
        """Create batches keeping sections together.
        
        Args:
            super_chunks: Super-chunks to batch
            
        Returns:
            List of batches
        """
        batches = []
        current_batch = SuperChunkBatch(batch_index=0)
        
        for super_chunk in super_chunks:
            # Check if adding would exceed batch limit
            if (current_batch.total_tokens + super_chunk.total_tokens > self.max_tokens_per_batch
                    and current_batch.super_chunks):
                # Save current batch and start new one
                batches.append(current_batch)
                current_batch = SuperChunkBatch(batch_index=len(batches))
            
            current_batch.add_super_chunk(super_chunk)
        
        # Save final batch
        if current_batch.super_chunks:
            batches.append(current_batch)
        
        LOGGER.info(
            "Created section-based batches",
            extra={
                "batch_count": len(batches),
                "total_super_chunks": sum(len(b.super_chunks) for b in batches),
            }
        )
        
        return batches
    
    def _batch_by_tokens(
        self,
        super_chunks: List[SectionSuperChunk],
    ) -> List[SuperChunkBatch]:
        """Create batches optimizing for token count.
        
        Args:
            super_chunks: Super-chunks to batch
            
        Returns:
            List of batches
        """
        batches = []
        current_batch = SuperChunkBatch(batch_index=0)
        
        # Sort by token count (smallest first) for better packing
        sorted_chunks = sorted(super_chunks, key=lambda sc: sc.total_tokens)
        
        for super_chunk in sorted_chunks:
            if (current_batch.total_tokens + super_chunk.total_tokens > self.max_tokens_per_batch
                    and current_batch.super_chunks):
                batches.append(current_batch)
                current_batch = SuperChunkBatch(batch_index=len(batches))
            
            current_batch.add_super_chunk(super_chunk)
        
        if current_batch.super_chunks:
            batches.append(current_batch)
        
        return batches
    
    def merge_small_super_chunks(
        self,
        super_chunks: List[SectionSuperChunk],
        min_tokens: int = 500,
    ) -> List[SectionSuperChunk]:
        """Merge small super-chunks of the same section type.
        
        Args:
            super_chunks: List of super-chunks
            min_tokens: Minimum tokens to avoid merging
            
        Returns:
            List of merged super-chunks
        """
        if not super_chunks:
            return []
        
        # Group by section type
        by_section: Dict[SectionType, List[SectionSuperChunk]] = {}
        for sc in super_chunks:
            if sc.section_type not in by_section:
                by_section[sc.section_type] = []
            by_section[sc.section_type].append(sc)
        
        merged = []
        for section_type, section_scs in by_section.items():
            if len(section_scs) == 1:
                merged.extend(section_scs)
                continue
            
            # Try to merge small ones
            current: Optional[SectionSuperChunk] = None
            
            for sc in section_scs:
                if sc.total_tokens >= min_tokens:
                    if current:
                        merged.append(current)
                        current = None
                    merged.append(sc)
                else:
                    if current is None:
                        current = sc
                    elif current.total_tokens + sc.total_tokens <= self.max_tokens_per_super_chunk:
                        # Merge
                        for chunk in sc.chunks:
                            current.add_chunk(chunk)
                    else:
                        merged.append(current)
                        current = sc
            
            if current:
                merged.append(current)
        
        # Re-sort by priority
        merged.sort(key=lambda sc: sc.processing_priority)
        
        return merged
    
    def get_extraction_order(
        self,
        super_chunks: List[SectionSuperChunk],
    ) -> List[SectionSuperChunk]:
        """Get super-chunks in optimal extraction order.
        
        Orders super-chunks for sequential extraction according to extraction processing model.
        
        Args:
            super_chunks: List of super-chunks
            
        Returns:
            Ordered list for extraction
        """
        # Separate by processing type
        llm_required = [sc for sc in super_chunks if sc.requires_llm]
        table_only = [sc for sc in super_chunks if sc.table_only]
        
        # Sort each group by priority
        llm_required.sort(key=lambda sc: sc.processing_priority)
        table_only.sort(key=lambda sc: sc.processing_priority)
        
        # LLM sections first, then table-only
        return llm_required + table_only
    
    def estimate_llm_calls(
        self,
        super_chunks: List[SectionSuperChunk],
    ) -> Dict[str, Any]:
        """Estimate number of LLM API calls needed.
        
        Args:
            super_chunks: List of super-chunks
            
        Returns:
            Dict with estimation details
        """
        llm_required = [sc for sc in super_chunks if sc.requires_llm]
        table_only = [sc for sc in super_chunks if sc.table_only]
        
        # Create batches to estimate calls
        batches = self.create_processing_batches(llm_required)
        
        total_tokens = sum(sc.total_tokens for sc in llm_required)
        
        return {
            "tier1_calls": 1,  # Document classification
            "tier2_calls": len(batches),  # Section extraction
            "tier3_calls": 1,  # Cross-section validation
            "total_llm_calls": 2 + len(batches),
            "table_only_sections": len(table_only),
            "total_llm_tokens": total_tokens,
            "sections_requiring_llm": [sc.section_type.value for sc in llm_required],
            "sections_table_only": [sc.section_type.value for sc in table_only],
        }

