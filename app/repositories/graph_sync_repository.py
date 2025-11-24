"""Repository for managing Neo4j graph synchronization state.

This repository handles CRUD operations for graph sync state,
tracking which entities have been synced to Neo4j and their node IDs.
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import GraphSyncState
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GraphSyncRepository:
    """Repository for managing Neo4j graph synchronization state.
    
    This repository provides data access methods for tracking entity
    synchronization to Neo4j, including node IDs and sync status.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize graph sync repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def create_sync_state(
        self,
        entity_id: UUID,
        entity_type: str,
        neo4j_node_id: Optional[str] = None,
        status: str = "pending"
    ) -> GraphSyncState:
        """Create initial sync state for an entity.
        
        Args:
            entity_id: ID of the canonical entity
            entity_type: Type of entity (POLICY_NUMBER, CLAIM_NUMBER, etc.)
            neo4j_node_id: Neo4j node ID (if already synced)
            status: Initial status (default: "pending")
            
        Returns:
            GraphSyncState: The created sync state record
            
        Example:
            >>> repo = GraphSyncRepository(session)
            >>> sync_state = await repo.create_sync_state(
            ...     entity_id=entity_uuid,
            ...     entity_type="POLICY_NUMBER"
            ... )
        """
        sync_state = GraphSyncState(
            entity_id=entity_id,
            entity_type=entity_type,
            neo4j_node_id=neo4j_node_id,
            sync_status=status,
            last_synced_at=None,
            sync_error=None
        )
        
        self.session.add(sync_state)
        await self.session.flush()
        
        LOGGER.debug(
            "Graph sync state created",
            extra={
                "entity_id": str(entity_id),
                "entity_type": entity_type,
                "status": status,
                "neo4j_node_id": neo4j_node_id
            }
        )
        
        return sync_state
    
    async def get_sync_state(
        self,
        entity_id: UUID
    ) -> Optional[GraphSyncState]:
        """Get sync state for an entity.
        
        Args:
            entity_id: ID of the canonical entity
            
        Returns:
            Optional[GraphSyncState]: The sync state if found, None otherwise
        """
        query = select(GraphSyncState).where(
            GraphSyncState.entity_id == entity_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def update_sync_status(
        self,
        entity_id: UUID,
        neo4j_node_id: Optional[str],
        status: str,
        error: Optional[str] = None
    ) -> Optional[GraphSyncState]:
        """Update sync status for an entity.
        
        Args:
            entity_id: ID of the canonical entity
            neo4j_node_id: Neo4j node ID (set when synced)
            status: New status ('pending', 'synced', 'failed')
            error: Error message if status is 'failed'
            
        Returns:
            Optional[GraphSyncState]: Updated sync state, None if not found
        """
        sync_state = await self.get_sync_state(entity_id)
        
        if not sync_state:
            LOGGER.warning(
                "Sync state not found for update",
                extra={"entity_id": str(entity_id)}
            )
            return None
        
        sync_state.sync_status = status
        sync_state.sync_error = error
        
        if neo4j_node_id:
            sync_state.neo4j_node_id = neo4j_node_id
        
        if status == "synced":
            sync_state.last_synced_at = datetime.now(timezone.utc)
        
        await self.session.flush()
        
        LOGGER.info(
            "Graph sync status updated",
            extra={
                "entity_id": str(entity_id),
                "status": status,
                "neo4j_node_id": neo4j_node_id,
                "has_error": error is not None
            }
        )
        
        return sync_state
    
    async def get_unsynced_entities(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100
    ) -> List[GraphSyncState]:
        """Get entities pending Neo4j sync.
        
        Args:
            entity_type: Filter by entity type (optional)
            limit: Maximum number of results
            
        Returns:
            List[GraphSyncState]: List of sync states pending sync
        """
        query = select(GraphSyncState).where(
            GraphSyncState.sync_status == "pending"
        )
        
        if entity_type:
            query = query.where(GraphSyncState.entity_type == entity_type)
        
        query = query.limit(limit)
        
        result = await self.session.execute(query)
        unsynced_states = list(result.scalars().all())
        
        LOGGER.info(
            "Retrieved unsynced entities",
            extra={
                "count": len(unsynced_states),
                "entity_type": entity_type,
                "limit": limit
            }
        )
        
        return unsynced_states
    
    async def get_failed_syncs(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100
    ) -> List[GraphSyncState]:
        """Get entities with failed Neo4j sync.
        
        Args:
            entity_type: Filter by entity type (optional)
            limit: Maximum number of results
            
        Returns:
            List[GraphSyncState]: List of sync states with failures
        """
        query = select(GraphSyncState).where(
            GraphSyncState.sync_status == "failed"
        )
        
        if entity_type:
            query = query.where(GraphSyncState.entity_type == entity_type)
        
        query = query.limit(limit)
        
        result = await self.session.execute(query)
        failed_states = list(result.scalars().all())
        
        LOGGER.info(
            "Retrieved failed syncs",
            extra={
                "count": len(failed_states),
                "entity_type": entity_type,
                "limit": limit
            }
        )
        
        return failed_states
    
    async def mark_for_resync(
        self,
        entity_id: UUID
    ) -> Optional[GraphSyncState]:
        """Mark entity for re-sync (e.g., after entity update).
        
        Args:
            entity_id: ID of the canonical entity
            
        Returns:
            Optional[GraphSyncState]: Updated sync state, None if not found
        """
        sync_state = await self.get_sync_state(entity_id)
        
        if not sync_state:
            LOGGER.warning(
                "Sync state not found for resync",
                extra={"entity_id": str(entity_id)}
            )
            return None
        
        sync_state.sync_status = "pending"
        sync_state.sync_error = None
        # Keep neo4j_node_id for update operation
        
        await self.session.flush()
        
        LOGGER.info(
            "Entity marked for resync",
            extra={
                "entity_id": str(entity_id),
                "neo4j_node_id": sync_state.neo4j_node_id
            }
        )
        
        return sync_state
    
    async def get_synced_entities_by_type(
        self,
        entity_type: str,
        limit: int = 100
    ) -> List[GraphSyncState]:
        """Get successfully synced entities of a specific type.
        
        Args:
            entity_type: Entity type to filter by
            limit: Maximum number of results
            
        Returns:
            List[GraphSyncState]: List of synced entities
        """
        query = (
            select(GraphSyncState)
            .where(
                GraphSyncState.entity_type == entity_type,
                GraphSyncState.sync_status == "synced"
            )
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        synced_states = list(result.scalars().all())
        
        LOGGER.info(
            "Retrieved synced entities by type",
            extra={
                "count": len(synced_states),
                "entity_type": entity_type,
                "limit": limit
            }
        )
        
        return synced_states
    
    async def get_sync_stats(self) -> dict:
        """Get sync statistics.
        
        Returns:
            dict: Statistics including counts by status
        """
        from sqlalchemy import func
        
        query = select(
            GraphSyncState.sync_status,
            func.count(GraphSyncState.id).label('count')
        ).group_by(GraphSyncState.sync_status)
        
        result = await self.session.execute(query)
        stats = {row.sync_status: row.count for row in result}
        
        LOGGER.debug("Retrieved sync stats", extra={"stats": stats})
        
        return stats
