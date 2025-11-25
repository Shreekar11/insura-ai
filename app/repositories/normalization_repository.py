from typing import List, Optional, Dict, Any
from uuid import UUID
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_repository import BaseRepository
from app.database.models import NormalizedChunk, DocumentChunk
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NormalizationRepository(BaseRepository[NormalizedChunk]):
    """Repository for managing normalized chunks.
    
    Inherits from BaseRepository for standard CRUD operations.
    Provides specialized methods for normalization-specific logic.
    """

    def __init__(self, session: AsyncSession):
        """Initialize normalization repository.
        
        Args:
            session: SQLAlchemy async session
        """
        super().__init__(session, NormalizedChunk)

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
        """
        # Compute content hash for change detection
        content_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
        
        return await self.create(
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

    async def get_normalized_chunks_by_document(
        self, 
        document_id: UUID
    ) -> List[NormalizedChunk]:
        """Get all normalized chunks for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List[NormalizedChunk]: List of normalized chunks ordered by page and chunk index
        """
        try:
            query = (
                select(NormalizedChunk)
                .join(DocumentChunk, NormalizedChunk.chunk_id == DocumentChunk.id)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
            )
            
            result = await self.session.execute(query)
            chunks = list(result.scalars().all())
            
            self.logger.debug(
                "Retrieved normalized chunks",
                extra={
                    "document_id": str(document_id),
                    "chunk_count": len(chunks),
                }
            )
            
            return chunks
        except Exception as e:
            self.logger.error(f"Error retrieving chunks for document {document_id}: {e}")
            raise

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
        try:
            query = select(NormalizedChunk).where(NormalizedChunk.chunk_id == chunk_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            self.logger.error(f"Error retrieving normalized chunk {chunk_id}: {e}")
            raise

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
            self.logger.warning(
                "Normalized chunk not found for update",
                extra={"chunk_id": str(chunk_id)}
            )
            return False
        
        updates = {}
        
        if normalized_text is not None:
            updates["normalized_text"] = normalized_text
            # Recompute hash if text changes
            updates["content_hash"] = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
            
        if processing_time_ms is not None:
            updates["processing_time_ms"] = processing_time_ms
            
        if pipeline_run_id is not None:
            updates["pipeline_run_id"] = pipeline_run_id
            
        if extracted_fields is not None:
            updates["extracted_fields"] = extracted_fields
            
        if entities is not None:
            updates["entities"] = entities
            
        if relationships is not None:
            updates["relationships"] = relationships
            
        if quality_score is not None:
            updates["quality_score"] = quality_score
            
        if updates:
            # Use the base update method (passing the ID of the NormalizedChunk record, not chunk_id)
            # Wait, get_normalized_chunk_by_id returns the record, so we have its ID
            await self.update(chunk.id, **updates)
            
            self.logger.info(
                "Normalized chunk updated",
                extra={
                    "chunk_id": str(chunk_id),
                    "updates": list(updates.keys())
                }
            )
            return True
            
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
        
        Args:
            document_id: Document ID
            
        Returns:
            List[UUID]: List of chunk IDs needing reprocessing
        """
        try:
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
        except Exception as e:
            self.logger.error(f"Error finding chunks needing reprocessing: {e}")
            raise

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
        
        self.logger.info(
            "Deleted normalized chunks",
            extra={
                "document_id": str(document_id),
                "count": count,
            }
        )
        
        return count
