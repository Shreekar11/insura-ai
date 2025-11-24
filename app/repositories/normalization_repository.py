"""Repository for normalization-related database operations.

This repository handles all data access operations related to document
normalization, including creating and retrieving normalized chunks.
"""

from typing import List, Optional
from uuid import UUID
import hashlib
from datetime import datetime, timezone

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
        extracted_fields: Optional[dict] = None,
        entities: Optional[dict] = None,
        relationships: Optional[dict] = None,
        model_version: Optional[str] = None,
        prompt_version: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
        source_stage: Optional[str] = "normalization",
        quality_score: Optional[float] = None,
    ) -> NormalizedChunk:
        """Create a normalized chunk record.
        
        Args:
            chunk_id: ID of the document chunk being normalized
            normalized_text: The normalized text content
            method: Normalization method used (e.g., "llm", "hybrid")
            processing_time_ms: Time taken to normalize in milliseconds
            extracted_fields: Structured fields extracted during normalization
            entities: Extracted entities (JSONB)
            relationships: Extracted relationships (JSONB)
            model_version: LLM model version used
            prompt_version: Prompt template version
            pipeline_run_id: Pipeline execution identifier
            source_stage: Pipeline stage (normalization, extraction, etc.)
            quality_score: Quality score of normalization (0.0-1.0)
            
        Returns:
            NormalizedChunk: The created normalized chunk record
            
        Example:
            >>> repo = NormalizationRepository(session)
            >>> chunk = await repo.create_normalized_chunk(
            ...     chunk_id=chunk_uuid,
            ...     normalized_text="Clean normalized text",
            ...     method="llm",
            ...     processing_time_ms=250,
            ...     extracted_fields={"dates": [], "amounts": []},
            ...     entities={"entities": [...]},
            ...     relationships={"relationships": [...]},
            ...     pipeline_run_id="run_123"
            ... )
        """
        # Compute content hash for change detection
        content_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
        
        norm_chunk = NormalizedChunk(
            chunk_id=chunk_id,
            normalized_text=normalized_text,
            normalization_method=method,
            processing_time_ms=processing_time_ms,
            extracted_fields=extracted_fields,
            entities=entities,
            relationships=relationships,
            content_hash=content_hash,
            model_version=model_version,
            prompt_version=prompt_version,
            pipeline_run_id=pipeline_run_id,
            source_stage=source_stage,
            quality_score=quality_score,
            extracted_at=datetime.now(timezone.utc),
        )
        self.session.add(norm_chunk)
        await self.session.flush()
        
        LOGGER.debug(
            "Normalized chunk created",
            extra={
                "chunk_id": str(chunk_id),
                "method": method,
                "text_length": len(normalized_text),
                "content_hash": content_hash[:16],
                "processing_time_ms": processing_time_ms,
                "entities_count": len(entities.get("entities", [])) if entities else 0,
                "relationships_count": len(relationships.get("relationships", [])) if relationships else 0,
                "pipeline_run_id": pipeline_run_id,
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
        normalized_text: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        pipeline_run_id: Optional[str] = None,
        extracted_fields: Optional[dict] = None,
        entities: Optional[dict] = None,
        relationships: Optional[dict] = None,
        quality_score: Optional[float] = None,
    ) -> bool:
        """Update an existing normalized chunk.
        
        Args:
            chunk_id: ID of the chunk to update
            normalized_text: New normalized text (optional)
            processing_time_ms: Updated processing time (optional)
            pipeline_run_id: Pipeline execution identifier (optional)
            extracted_fields: Structured fields (optional)
            entities: Extracted entities (optional)
            relationships: Extracted relationships (optional)
            quality_score: Quality score (optional)
            
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
        
        if normalized_text is not None:
            chunk.normalized_text = normalized_text
            # Recompute hash if text changes
            chunk.content_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
            
        if processing_time_ms is not None:
            chunk.processing_time_ms = processing_time_ms
            
        if pipeline_run_id is not None:
            chunk.pipeline_run_id = pipeline_run_id
            
        if extracted_fields is not None:
            chunk.extracted_fields = extracted_fields
            
        if entities is not None:
            chunk.entities = entities
            
        if relationships is not None:
            chunk.relationships = relationships
            
        if quality_score is not None:
            chunk.quality_score = quality_score
            
        chunk.updated_at = datetime.now(timezone.utc)
        
        await self.session.flush()
        
        LOGGER.info(
            "Normalized chunk updated",
            extra={
                "chunk_id": str(chunk_id),
                "has_text_update": normalized_text is not None,
                "pipeline_run_id": pipeline_run_id
            }
        )
        
        return True

    async def check_content_changed(
        self,
        chunk_id: UUID,
        new_content_hash: str
    ) -> bool:
        """Check if normalized content has changed.
        
        Args:
            chunk_id: Chunk ID to check
            new_content_hash: SHA256 hash of new normalized text
            
        Returns:
            bool: True if content changed or doesn't exist, False if unchanged
        """
        existing = await self.get_normalized_chunk_by_id(chunk_id)
        if not existing:
            return True  # New chunk
        
        if not existing.content_hash:
            return True  # No hash stored, assume changed
        
        return existing.content_hash != new_content_hash

    async def get_chunks_needing_reprocessing(
        self,
        document_id: UUID
    ) -> List[UUID]:
        """Get chunk IDs that need reprocessing.
        
        Returns chunks where:
        - No normalized chunk exists
        - content_hash is NULL
        
        Note: This is a helper to find chunks that definitely need processing.
        For content changes, use check_content_changed during processing.
        
        Args:
            document_id: Document ID
            
        Returns:
            List[UUID]: List of chunk IDs needing reprocessing
        """
        from app.database.models import DocumentChunk
        
        # Find chunks that don't have a normalized chunk or have null hash
        query = (
            select(DocumentChunk.id)
            .outerjoin(NormalizedChunk, DocumentChunk.id == NormalizedChunk.chunk_id)
            .where(
                DocumentChunk.document_id == document_id,
                (NormalizedChunk.id == None) | (NormalizedChunk.content_hash == None)
            )
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

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
