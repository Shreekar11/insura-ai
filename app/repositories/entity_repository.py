import uuid
from typing import Optional, List, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import CanonicalEntity, EntityRelationship, WorkflowEntityScope, WorkflowRelationshipScope
from app.repositories.base_repository import BaseRepository

class EntityRepository(BaseRepository[CanonicalEntity]):
    """Repository for managing CanonicalEntity records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, CanonicalEntity)

    async def get_by_key(self, entity_type: str, canonical_key: str) -> Optional[CanonicalEntity]:
        """Get canonical entity by type and key."""
        query = select(CanonicalEntity).where(
            CanonicalEntity.entity_type == entity_type,
            CanonicalEntity.canonical_key == canonical_key
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def add_to_workflow_scope(self, workflow_id: uuid.UUID, canonical_entity_id: uuid.UUID) -> None:
        """Add a canonical entity to a workflow scope (idempotent)."""
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(WorkflowEntityScope).values(
            workflow_id=workflow_id,
            canonical_entity_id=canonical_entity_id
        ).on_conflict_do_nothing()
        await self.session.execute(stmt)
        await self.session.flush()


class EntityRelationshipRepository(BaseRepository[EntityRelationship]):
    """Repository for managing EntityRelationship records."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, EntityRelationship)

    async def add_to_workflow_scope(self, workflow_id: uuid.UUID, relationship_id: uuid.UUID) -> None:
        """Add an entity relationship to a workflow scope (idempotent)."""
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(WorkflowRelationshipScope).values(
            workflow_id=workflow_id,
            relationship_id=relationship_id
        ).on_conflict_do_nothing()
        await self.session.execute(stmt)
        await self.session.flush()
