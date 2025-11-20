"""Repository for normalization-related database operations.

This repository handles all data access operations related to document
normalization, including creating and retrieving normalized chunks.
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import NormalizedChunk
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NormalizationRepository:
    """Repository for managing normalized chunks.
    
    This repository provides data access methods for normalized chunk
    operations, separating database logic from business logic.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession):
        """Initialize normalization repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_normalized_chunk(
        self,
        chunk_id: UUID,
        normalized_text: str,
        method: str = "llm",
        processing_time_ms: Optional[int] = None,
    ) -> NormalizedChunk:
        """Create a normalized chunk record.
        
        Args:
            chunk_id: ID of the document chunk being normalized
            normalized_text: The normalized text content
            method: Normalization method used (e.g., "llm", "hybrid")
            processing_time_ms: Time taken to normalize in milliseconds
            
        Returns:
            NormalizedChunk: The created normalized chunk record
            
        Example:
            >>> repo = NormalizationRepository(session)
            >>> chunk = await repo.create_normalized_chunk(
            ...     chunk_id=chunk_uuid,
            ...     normalized_text="Clean normalized text",
            ...     method="llm",
            ...     processing_time_ms=250
            ... )
        """
        norm_chunk = NormalizedChunk(
            chunk_id=chunk_id,
            normalized_text=normalized_text,
            normalization_method=method,
            processing_time_ms=processing_time_ms,
        )
        self.session.add(norm_chunk)
        await self.session.flush()
        
        LOGGER.debug(
            "Normalized chunk created",
            extra={
                "chunk_id": str(chunk_id),
                "method": method,
                "text_length": len(normalized_text),
                "processing_time_ms": processing_time_ms,
            }
        )
        
        return norm_chunk

    async def get_normalized_chunks_by_document(
        self, 
        document_id: UUID
    ) -> List[NormalizedChunk]:
        """Get all normalized chunks for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List[NormalizedChunk]: List of normalized chunks ordered by page and chunk index
            
        Example:
            >>> repo = NormalizationRepository(session)
            >>> chunks = await repo.get_normalized_chunks_by_document(doc_id)
            >>> for chunk in chunks:
            ...     print(chunk.normalized_text)
        """
        # Join with DocumentChunk to get ordering information
        from app.database.models import DocumentChunk
        
        query = (
            select(NormalizedChunk)
            .join(DocumentChunk, NormalizedChunk.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        LOGGER.debug(
            "Retrieved normalized chunks",
            extra={
                "document_id": str(document_id),
                "chunk_count": len(chunks),
            }
        )
        
        return chunks

    async def get_normalized_chunk_by_id(
        self, 
        chunk_id: UUID
    ) -> Optional[NormalizedChunk]:
        """Get a specific normalized chunk by its chunk ID.
        
        Args:
            chunk_id: ID of the document chunk
            
        Returns:
            Optional[NormalizedChunk]: The normalized chunk if found, None otherwise
        """
        query = select(NormalizedChunk).where(NormalizedChunk.chunk_id == chunk_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def update_normalized_chunk(
        self,
        chunk_id: UUID,
        normalized_text: str,
        processing_time_ms: Optional[int] = None,
    ) -> bool:
        """Update an existing normalized chunk.
        
        Args:
            chunk_id: ID of the chunk to update
            normalized_text: New normalized text
            processing_time_ms: Updated processing time
            
        Returns:
            bool: True if updated successfully, False if chunk not found
        """
        chunk = await self.get_normalized_chunk_by_id(chunk_id)
        if not chunk:
            LOGGER.warning(
                "Normalized chunk not found for update",
                extra={"chunk_id": str(chunk_id)}
            )
            return False
        
        chunk.normalized_text = normalized_text
        if processing_time_ms is not None:
            chunk.processing_time_ms = processing_time_ms
        
        await self.session.flush()
        
        LOGGER.info(
            "Normalized chunk updated",
            extra={"chunk_id": str(chunk_id)}
        )
        
        return True

    async def delete_normalized_chunks_by_document(
        self, 
        document_id: UUID
    ) -> int:
        """Delete all normalized chunks for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            int: Number of chunks deleted
        """
        chunks = await self.get_normalized_chunks_by_document(document_id)
        count = len(chunks)
        
        for chunk in chunks:
            await self.session.delete(chunk)
        
        await self.session.flush()
        
        LOGGER.info(
            "Deleted normalized chunks",
            extra={
                "document_id": str(document_id),
                "count": count,
            }
        )
        
        return count
