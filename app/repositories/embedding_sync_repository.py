"""Repository for managing embedding synchronization state.

This repository handles CRUD operations for embedding sync state,
tracking which chunks have embeddings generated and their versions.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EmbeddingSyncState
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EmbeddingSyncRepository:
    """Repository for managing embedding synchronization state.
    
    This repository provides data access methods for tracking embedding
    generation, versioning, and sync status for vector indexing.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize embedding sync repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def create_sync_state(
        self,
        chunk_id: UUID,
        embedding_model: str,
        embedding_version: str,
        vector_dimension: int,
        status: str = "pending"
    ) -> EmbeddingSyncState:
        """Create initial sync state for a chunk.
        
        Args:
            chunk_id: ID of the chunk
            embedding_model: Model used for embedding (e.g., "mistral-embed")
            embedding_version: Version of the embedding model
            vector_dimension: Dimension of the embedding vector
            status: Initial status (default: "pending")
            
        Returns:
            EmbeddingSyncState: The created sync state record
            
        Example:
            >>> repo = EmbeddingSyncRepository(session)
            >>> sync_state = await repo.create_sync_state(
            ...     chunk_id=chunk_uuid,
            ...     embedding_model="mistral-embed",
            ...     embedding_version="v1.0",
            ...     vector_dimension=1024
            ... )
        """
        sync_state = EmbeddingSyncState(
            chunk_id=chunk_id,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            vector_dimension=vector_dimension,
            sync_status=status,
            last_synced_at=None,
            sync_error=None
        )
        
        self.session.add(sync_state)
        await self.session.flush()
        
        LOGGER.debug(
            "Embedding sync state created",
            extra={
                "chunk_id": str(chunk_id),
                "embedding_model": embedding_model,
                "embedding_version": embedding_version,
                "status": status
            }
        )
        
        return sync_state
    
    async def get_sync_state(
        self,
        chunk_id: UUID
    ) -> Optional[EmbeddingSyncState]:
        """Get sync state for a chunk.
        
        Args:
            chunk_id: ID of the chunk
            
        Returns:
            Optional[EmbeddingSyncState]: The sync state if found, None otherwise
        """
        query = select(EmbeddingSyncState).where(
            EmbeddingSyncState.chunk_id == chunk_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def update_sync_status(
        self,
        chunk_id: UUID,
        status: str,
        error: Optional[str] = None
    ) -> Optional[EmbeddingSyncState]:
        """Update sync status for a chunk.
        
        Args:
            chunk_id: ID of the chunk
            status: New status ('pending', 'synced', 'failed')
            error: Error message if status is 'failed'
            
        Returns:
            Optional[EmbeddingSyncState]: Updated sync state, None if not found
        """
        sync_state = await self.get_sync_state(chunk_id)
        
        if not sync_state:
            LOGGER.warning(
                "Sync state not found for update",
                extra={"chunk_id": str(chunk_id)}
            )
            return None
        
        sync_state.sync_status = status
        sync_state.sync_error = error
        
        if status == "synced":
            sync_state.last_synced_at = datetime.now(timezone.utc)
        
        await self.session.flush()
        
        LOGGER.info(
            "Embedding sync status updated",
            extra={
                "chunk_id": str(chunk_id),
                "status": status,
                "has_error": error is not None
            }
        )
        
        return sync_state
    
    async def get_stale_embeddings(
        self,
        current_model_version: str,
        limit: int = 100
    ) -> List[EmbeddingSyncState]:
        """Get chunks with outdated embeddings.
        
        Args:
            current_model_version: Current embedding model version
            limit: Maximum number of results
            
        Returns:
            List[EmbeddingSyncState]: List of sync states with outdated embeddings
        """
        query = (
            select(EmbeddingSyncState)
            .where(
                EmbeddingSyncState.embedding_version != current_model_version,
                EmbeddingSyncState.sync_status == "synced"
            )
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        stale_states = list(result.scalars().all())
        
        LOGGER.info(
            "Retrieved stale embeddings",
            extra={
                "count": len(stale_states),
                "current_version": current_model_version,
                "limit": limit
            }
        )
        
        return stale_states
    
    async def get_unsynced_chunks(
        self,
        limit: int = 100
    ) -> List[EmbeddingSyncState]:
        """Get chunks pending embedding generation.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List[EmbeddingSyncState]: List of sync states pending embedding
        """
        query = (
            select(EmbeddingSyncState)
            .where(EmbeddingSyncState.sync_status == "pending")
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        unsynced_states = list(result.scalars().all())
        
        LOGGER.info(
            "Retrieved unsynced chunks",
            extra={"count": len(unsynced_states), "limit": limit}
        )
        
        return unsynced_states
    
    async def get_failed_syncs(
        self,
        limit: int = 100
    ) -> List[EmbeddingSyncState]:
        """Get chunks with failed embedding generation.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List[EmbeddingSyncState]: List of sync states with failures
        """
        query = (
            select(EmbeddingSyncState)
            .where(EmbeddingSyncState.sync_status == "failed")
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        failed_states = list(result.scalars().all())
        
        LOGGER.info(
            "Retrieved failed syncs",
            extra={"count": len(failed_states), "limit": limit}
        )
        
        return failed_states
    
    async def mark_for_resync(
        self,
        chunk_id: UUID
    ) -> Optional[EmbeddingSyncState]:
        """Mark chunk for re-embedding (e.g., after content change).
        
        Args:
            chunk_id: ID of the chunk
            
        Returns:
            Optional[EmbeddingSyncState]: Updated sync state, None if not found
        """
        sync_state = await self.get_sync_state(chunk_id)
        
        if not sync_state:
            LOGGER.warning(
                "Sync state not found for resync",
                extra={"chunk_id": str(chunk_id)}
            )
            return None
        
        sync_state.sync_status = "pending"
        sync_state.sync_error = None
        
        await self.session.flush()
        
        LOGGER.info(
            "Chunk marked for resync",
            extra={"chunk_id": str(chunk_id)}
        )
        
        return sync_state
