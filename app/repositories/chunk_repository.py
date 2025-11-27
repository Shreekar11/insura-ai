"""Repository for document chunks.

This repository handles CRUD operations for document chunks only.
Normalization and classification operations have been moved to dedicated repositories.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ChunkRepository:
    """Repository for managing document chunks.
    
    This repository provides data access methods for document chunk operations,
    focusing solely on chunk CRUD (Create, Read, Update, Delete) operations.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession):
        """Initialize chunk repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def create_chunk(
        self,
        document_id: UUID,
        page_number: int,
        chunk_index: int,
        raw_text: str,
        token_count: int,
        section_name: Optional[str] = None,
        stable_chunk_id: Optional[str] = None,
        section_type: Optional[str] = None,
        subsection_type: Optional[str] = None,
    ) -> DocumentChunk:
        """Create a new document chunk.
        
        Args:
            document_id: ID of the parent document
            page_number: Page number where chunk appears
            chunk_index: Index of chunk within the page
            raw_text: Raw text content of the chunk
            token_count: Number of tokens in the chunk
            section_name: Optional section name for the chunk
            stable_chunk_id: Deterministic chunk ID
            section_type: High-level section type
            subsection_type: Fine-grained subsection type
            
        Returns:
            DocumentChunk: The created chunk record
            
        Example:
            >>> repo = ChunkRepository(session)
            >>> chunk = await repo.create_chunk(
            ...     document_id=doc_uuid,
            ...     page_number=1,
            ...     chunk_index=0,
            ...     raw_text="Policy details...",
            ...     token_count=150,
            ...     section_name="Policy Declarations",
            ...     stable_chunk_id="doc_..._p1_c0"
            ... )
        """
        chunk = DocumentChunk(
            document_id=document_id,
            page_number=page_number,
            chunk_index=chunk_index,
            raw_text=raw_text,
            token_count=token_count,
            section_name=section_name,
            stable_chunk_id=stable_chunk_id,
            section_type=section_type,
            subsection_type=subsection_type,
        )
        self.session.add(chunk)
        await self.session.flush()
        
        LOGGER.debug(
            "Document chunk created",
            extra={
                "document_id": str(document_id),
                "page_number": page_number,
                "chunk_index": chunk_index,
                "token_count": token_count,
            }
        )
        
        return chunk

    async def get_chunks_by_document(
        self, 
        document_id: UUID
    ) -> List[DocumentChunk]:
        """Get all chunks for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List[DocumentChunk]: List of chunks ordered by page and chunk index
            
        Example:
            >>> repo = ChunkRepository(session)
            >>> chunks = await repo.get_chunks_by_document(doc_id)
            >>> for chunk in chunks:
            ...     print(f"Page {chunk.page_number}, Chunk {chunk.chunk_index}")
        """
        query = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        result = await self.session.execute(query)
        chunks = list(result.scalars().all())
        
        LOGGER.debug(
            "Retrieved document chunks",
            extra={
                "document_id": str(document_id),
                "chunk_count": len(chunks),
            }
        )
        
        return chunks

    async def bulk_create_chunks(
        self,
        chunks_data: List[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        """Bulk create multiple document chunks efficiently.
        
        This method is optimized for batch processing, creating multiple
        chunks in a single transaction for better performance.
        
        Args:
            chunks_data: List of dictionaries containing chunk data.
                        Each dict should have: document_id, page_number,
                        chunk_index, raw_text, token_count, and optional
                        section_name, stable_chunk_id, section_type, subsection_type
                        
        Returns:
            List[DocumentChunk]: List of created chunk records
            
        Example:
            >>> chunks_data = [
            ...     {
            ...         "document_id": doc_id,
            ...         "page_number": 1,
            ...         "chunk_index": 0,
            ...         "raw_text": "text1",
            ...         "token_count": 100,
            ...         "stable_chunk_id": "doc_..._p1_c0"
            ...     },
            ...     {
            ...         "document_id": doc_id,
            ...         "page_number": 1,
            ...         "chunk_index": 1,
            ...         "raw_text": "text2",
            ...         "token_count": 120,
            ...         "stable_chunk_id": "doc_..._p1_c1"
            ...     }
            ... ]
            >>> chunks = await repo.bulk_create_chunks(chunks_data)
        """
        if not chunks_data:
            LOGGER.warning("Empty chunks_data provided to bulk_create_chunks")
            return []
        
        created_chunks = []
        
        for chunk_data in chunks_data:
            chunk = DocumentChunk(
                document_id=chunk_data["document_id"],
                page_number=chunk_data["page_number"],
                chunk_index=chunk_data["chunk_index"],
                raw_text=chunk_data["raw_text"],
                token_count=chunk_data["token_count"],
                section_name=chunk_data.get("section_name"),
                stable_chunk_id=chunk_data.get("stable_chunk_id"),
                section_type=chunk_data.get("section_type"),
                subsection_type=chunk_data.get("subsection_type"),
            )
            self.session.add(chunk)
            created_chunks.append(chunk)
        
        # Flush to get IDs assigned
        await self.session.flush()
        
        LOGGER.info(
            f"Bulk created {len(created_chunks)} document chunks",
            extra={
                "chunk_count": len(created_chunks),
                "document_id": str(chunks_data[0]["document_id"]) if chunks_data else None
            }
        )
        
        return created_chunks

    async def get_chunk_by_id(

        self, 
        chunk_id: UUID
    ) -> Optional[DocumentChunk]:
        """Get a specific chunk by ID.
        
        Args:
            chunk_id: ID of the chunk
            
        Returns:
            Optional[DocumentChunk]: The chunk if found, None otherwise
        """
        query = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_chunks_by_document(
        self, 
        document_id: UUID
    ) -> int:
        """Delete all chunks for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            int: Number of chunks deleted
        """
        chunks = await self.get_chunks_by_document(document_id)
        count = len(chunks)
        
        for chunk in chunks:
            await self.session.delete(chunk)
        
        await self.session.flush()
        
        LOGGER.info(
            "Deleted document chunks",
            extra={
                "document_id": str(document_id),
                "count": count,
            }
        )
        
        return count
