import uuid
from typing import Optional, List, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import CanonicalEntity, EntityRelationship, WorkflowEntityScope, WorkflowRelationshipScope, EntityEvidence
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

    async def get_by_document(self, document_id: uuid.UUID) -> Sequence[CanonicalEntity]:
        """Get all canonical entities associated with a specific document via evidence mapping."""
        query = (
            select(CanonicalEntity)
            .join(EntityEvidence, CanonicalEntity.id == EntityEvidence.canonical_entity_id)
            .where(EntityEvidence.document_id == document_id)
            .distinct()
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_workflow(self, workflow_id: uuid.UUID) -> Sequence[CanonicalEntity]:
        """Get all canonical entities associated with a specific workflow."""
        query = (
            select(CanonicalEntity)
            .join(WorkflowEntityScope, CanonicalEntity.id == WorkflowEntityScope.canonical_entity_id)
            .where(WorkflowEntityScope.workflow_id == workflow_id)
            .distinct()
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_with_provenance_by_document(self, document_id: uuid.UUID) -> Sequence[tuple[CanonicalEntity, str, str]]:
        """Get entities with their source section and chunk ID for a document."""
        from app.database.models import EntityMention, SectionExtraction
        query = (
            select(CanonicalEntity, EntityMention.source_stable_chunk_id, SectionExtraction.section_type)
            .join(EntityEvidence, CanonicalEntity.id == EntityEvidence.canonical_entity_id)
            .join(EntityMention, EntityEvidence.entity_mention_id == EntityMention.id)
            .outerjoin(SectionExtraction, EntityMention.section_extraction_id == SectionExtraction.id)
            .where(EntityEvidence.document_id == document_id)
        )
        result = await self.session.execute(query)
        return result.all()

    async def get_with_provenance_by_workflow(self, workflow_id: uuid.UUID) -> Sequence[tuple[CanonicalEntity, str, str]]:
        """Get entities with their source section and chunk ID for a workflow."""
        from app.database.models import EntityMention, SectionExtraction
        query = (
            select(CanonicalEntity, EntityMention.source_stable_chunk_id, SectionExtraction.section_type)
            .join(WorkflowEntityScope, CanonicalEntity.id == WorkflowEntityScope.canonical_entity_id)
            .join(EntityEvidence, CanonicalEntity.id == EntityEvidence.canonical_entity_id)
            .join(EntityMention, EntityEvidence.entity_mention_id == EntityMention.id)
            .outerjoin(SectionExtraction, EntityMention.section_extraction_id == SectionExtraction.id)
            .where(WorkflowEntityScope.workflow_id == workflow_id)
        )
        result = await self.session.execute(query)
        return result.all()

    async def get_canonical_keys_by_ids(
        self, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str]]:
        """Bulk fetch canonical_key and entity_type for a list of entity IDs.

        Returns:
            Dict mapping entity UUID to (canonical_key, entity_type).
        """
        if not ids:
            return {}
        query = select(
            CanonicalEntity.id, CanonicalEntity.canonical_key, CanonicalEntity.entity_type
        ).where(CanonicalEntity.id.in_(ids))
        result = await self.session.execute(query)
        return {row.id: (row.canonical_key, row.entity_type) for row in result}

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

    async def get_by_document(self, document_id: uuid.UUID) -> Sequence[EntityRelationship]:
        """Get all relationships for a specific document."""
        return await self.get_all(filters={"document_id": document_id})

    async def get_by_workflow(self, workflow_id: uuid.UUID) -> Sequence[EntityRelationship]:
        """Get all entity relationships associated with a specific workflow."""
        query = (
            select(EntityRelationship)
            .join(WorkflowRelationshipScope, EntityRelationship.id == WorkflowRelationshipScope.relationship_id)
            .where(WorkflowRelationshipScope.workflow_id == workflow_id)
            .distinct()
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def add_to_workflow_scope(self, workflow_id: uuid.UUID, relationship_id: uuid.UUID) -> None:
        """Add an entity relationship to a workflow scope (idempotent)."""
        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(WorkflowRelationshipScope).values(
            workflow_id=workflow_id,
            relationship_id=relationship_id
        ).on_conflict_do_nothing()
        await self.session.execute(stmt)
        await self.session.flush()
