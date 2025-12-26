"""Repository for section chunks and super-chunks.

This repository handles persistence of v2 hybrid chunks and section super-chunks,
supporting the section-aware extraction pipeline.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk, NormalizedChunk
from app.services.chunking.hybrid_models import (
    HybridChunk,
    HybridChunkMetadata,
    SectionType,
    SectionSuperChunk,
    ChunkingResult,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class SectionChunkRepository:
    """Repository for managing section-aware document chunks.
    
    This repository provides data access methods for v2 hybrid chunks
    and section super-chunks, including bulk operations and section-based
    queries.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize section chunk repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def save_chunking_result(
        self,
        result: ChunkingResult,
        document_id: UUID,
    ) -> List[DocumentChunk]:
        """Save all chunks from a chunking result.
        
        Args:
            result: ChunkingResult from hybrid chunking
            document_id: Document ID
            
        Returns:
            List of created DocumentChunk records
        """
        if not result.chunks:
            LOGGER.warning("Empty chunking result, nothing to save")
            return []
        
        LOGGER.info(
            "Saving chunking result",
            extra={
                "document_id": str(document_id),
                "chunk_count": len(result.chunks),
                "super_chunk_count": len(result.super_chunks),
            }
        )
        
        created_chunks = []
        
        for chunk in result.chunks:
            db_chunk = await self.create_hybrid_chunk(
                hybrid_chunk=chunk,
                document_id=document_id,
            )
            created_chunks.append(db_chunk)
        
        await self.session.flush()
        
        LOGGER.info(
            "Chunking result saved",
            extra={
                "document_id": str(document_id),
                "saved_count": len(created_chunks),
            }
        )
        
        return created_chunks
    
    async def create_hybrid_chunk(
        self,
        hybrid_chunk: HybridChunk,
        document_id: UUID,
    ) -> DocumentChunk:
        """Create a DocumentChunk from a HybridChunk.
        
        Args:
            hybrid_chunk: HybridChunk to persist
            document_id: Document ID
            
        Returns:
            Created DocumentChunk record
        """
        metadata = hybrid_chunk.metadata
        
        # Build additional metadata for JSONB storage
        additional_metadata = {
            "page_range": metadata.page_range,
            "chunk_role": metadata.chunk_role.value if metadata.chunk_role else None,
            "has_tables": metadata.has_tables,
            "table_count": metadata.table_count,
            "context_header": metadata.context_header,
            "source": metadata.source,
            "contextualized_text": hybrid_chunk.contextualized_text,
        }
        
        chunk = DocumentChunk(
            document_id=document_id,
            page_number=metadata.page_number,
            section_name=metadata.section_name,
            chunk_index=metadata.chunk_index,
            raw_text=hybrid_chunk.text,
            token_count=metadata.token_count,
            section_type=metadata.section_type.value if metadata.section_type else None,
            subsection_type=metadata.subsection_type,
            stable_chunk_id=metadata.stable_chunk_id,
        )
        
        self.session.add(chunk)
        await self.session.flush()
        
        LOGGER.debug(
            "Created hybrid chunk",
            extra={
                "document_id": str(document_id),
                "chunk_id": str(chunk.id),
                "section_type": metadata.section_type.value if metadata.section_type else None,
                "page_number": metadata.page_number,
            }
        )
        
        return chunk
    
    async def get_chunks_by_section(
        self,
        document_id: UUID,
        section_type: SectionType,
    ) -> List[DocumentChunk]:
        """Get all chunks for a specific section type.
        
        Args:
            document_id: Document ID
            section_type: Section type to filter by
            
        Returns:
            List of DocumentChunks for the section
        """
        query = (
            select(DocumentChunk)
            .where(
                and_(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.section_type == section_type.value,
                )
            )
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        LOGGER.debug(
            "Retrieved section chunks",
            extra={
                "document_id": str(document_id),
                "section_type": section_type.value,
                "chunk_count": len(chunks),
            }
        )
        
        return chunks
    
    async def get_section_summary(
        self,
        document_id: UUID,
    ) -> Dict[str, Any]:
        """Get summary of sections in a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Dict with section summary information
        """
        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        if not chunks:
            return {
                "document_id": str(document_id),
                "total_chunks": 0,
                "sections": {},
            }
        
        # Build section summary
        sections: Dict[str, Dict[str, Any]] = {}
        
        for chunk in chunks:
            section_type = chunk.section_type or "unknown"
            
            if section_type not in sections:
                sections[section_type] = {
                    "chunk_count": 0,
                    "total_tokens": 0,
                    "page_range": [],
                }
            
            sections[section_type]["chunk_count"] += 1
            sections[section_type]["total_tokens"] += chunk.token_count
            if chunk.page_number not in sections[section_type]["page_range"]:
                sections[section_type]["page_range"].append(chunk.page_number)
        
        # Sort page ranges
        for section in sections.values():
            section["page_range"] = sorted(section["page_range"])
        
        return {
            "document_id": str(document_id),
            "total_chunks": len(chunks),
            "total_tokens": sum(c.token_count for c in chunks),
            "sections": sections,
        }
    
    async def rebuild_super_chunks(
        self,
        document_id: UUID,
    ) -> List[SectionSuperChunk]:
        """Rebuild SectionSuperChunks from stored DocumentChunks.
        
        This is useful for reprocessing or when super-chunks need to be
        reconstructed from the database.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of reconstructed SectionSuperChunks
        """
        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        if not chunks:
            return []
        
        # Group by section type
        section_groups: Dict[str, List[DocumentChunk]] = {}
        
        for chunk in chunks:
            section_type = chunk.section_type or "unknown"
            if section_type not in section_groups:
                section_groups[section_type] = []
            section_groups[section_type].append(chunk)
        
        # Build super-chunks
        super_chunks = []
        
        for section_type_str, section_chunks in section_groups.items():
            try:
                section_type = SectionType(section_type_str)
            except ValueError:
                section_type = SectionType.UNKNOWN
            
            # Convert DocumentChunks to HybridChunks
            hybrid_chunks = []
            for db_chunk in section_chunks:
                metadata = HybridChunkMetadata(
                    document_id=db_chunk.document_id,
                    page_number=db_chunk.page_number,
                    section_type=section_type,
                    section_name=db_chunk.section_name,
                    subsection_type=db_chunk.subsection_type,
                    chunk_index=db_chunk.chunk_index,
                    token_count=db_chunk.token_count,
                    stable_chunk_id=db_chunk.stable_chunk_id,
                )
                
                hybrid_chunk = HybridChunk(
                    text=db_chunk.raw_text,
                    metadata=metadata,
                )
                hybrid_chunks.append(hybrid_chunk)
            
            # Create super-chunk
            super_chunk = SectionSuperChunk(
                section_type=section_type,
                section_name=section_type.value.replace("_", " ").title(),
                chunks=hybrid_chunks,
                document_id=document_id,
                super_chunk_id=f"sc_{str(document_id)}_{section_type.value}",
            )
            super_chunks.append(super_chunk)
        
        # Sort by priority
        super_chunks.sort(key=lambda sc: sc.processing_priority)
        
        LOGGER.info(
            "Rebuilt super-chunks from database",
            extra={
                "document_id": str(document_id),
                "super_chunk_count": len(super_chunks),
            }
        )
        
        return super_chunks
    
    async def delete_chunks_by_document(
        self,
        document_id: UUID,
    ) -> int:
        """Delete all chunks for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Number of chunks deleted
        """
        query = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        count = len(chunks)
        for chunk in chunks:
            await self.session.delete(chunk)
        
        await self.session.flush()
        
        LOGGER.info(
            "Deleted document chunks",
            extra={
                "document_id": str(document_id),
                "deleted_count": count,
            }
        )
        
        return count
    
    async def get_chunks_for_extraction(
        self,
        document_id: UUID,
        section_types: Optional[List[SectionType]] = None,
        exclude_table_only: bool = False,
    ) -> List[DocumentChunk]:
        """Get chunks ready for LLM extraction.
        
        Args:
            document_id: Document ID
            section_types: Optional filter for specific sections
            exclude_table_only: Whether to exclude table-only sections
            
        Returns:
            List of DocumentChunks for extraction
        """
        from app.services.chunking.hybrid_models import SECTION_CONFIG
        
        query = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
        
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        # Filter by section types if specified
        if section_types:
            section_values = [st.value for st in section_types]
            chunks = [c for c in chunks if c.section_type in section_values]
        
        # Exclude table-only sections if requested
        if exclude_table_only:
            table_only_sections = [
                st.value for st, config in SECTION_CONFIG.items()
                if config.get("table_only", False)
            ]
            chunks = [c for c in chunks if c.section_type not in table_only_sections]
        
        # Sort by page and chunk index
        chunks.sort(key=lambda c: (c.page_number, c.chunk_index))
        
        return chunks

