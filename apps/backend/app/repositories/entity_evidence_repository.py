"""Repository for entity evidence persistence.

This repository handles persistence of evidence mappings between
canonical entities and their source mentions.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EntityEvidence
from app.repositories.base_repository import BaseRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EntityEvidenceRepository(BaseRepository[EntityEvidence]):
    """Repository for managing entity evidence records.
    
    This repository provides data access methods for evidence mappings
    that link canonical entities to their source mentions.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize entity evidence repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def create_entity_evidence(
        self,
        canonical_entity_id: UUID,
        entity_mention_id: UUID,
        document_id: UUID,
        confidence: Optional[Decimal] = None,
        evidence_type: str = "extracted",
    ) -> EntityEvidence:
        """Create a new entity evidence record.
        
        Args:
            canonical_entity_id: Canonical entity ID
            entity_mention_id: Entity mention ID
            document_id: Document ID
            confidence: Evidence confidence (0.0-1.0)
            evidence_type: Evidence type (extracted, inferred, human_verified)
            
        Returns:
            Created EntityEvidence record
        """
        evidence = EntityEvidence(
            canonical_entity_id=canonical_entity_id,
            entity_mention_id=entity_mention_id,
            document_id=document_id,
            confidence=confidence,
            evidence_type=evidence_type,
        )
        
        self.session.add(evidence)
        await self.session.flush()
        
        LOGGER.debug(
            "Created entity evidence",
            extra={
                "canonical_entity_id": str(canonical_entity_id),
                "entity_mention_id": str(entity_mention_id),
                "evidence_id": str(evidence.id),
            }
        )
        
        return evidence
    
    async def create_batch(
        self,
        evidence_records: List[Dict[str, Any]],
    ) -> List[EntityEvidence]:
        """Create multiple entity evidence records in batch.
        
        Args:
            evidence_records: List of evidence dictionaries with required fields
            
        Returns:
            List of created EntityEvidence records
        """
        created_evidence = []
        
        for evidence_data in evidence_records:
            evidence = EntityEvidence(**evidence_data)
            self.session.add(evidence)
            created_evidence.append(evidence)
        
        await self.session.flush()
        
        LOGGER.debug(
            "Created batch of entity evidence",
            extra={"count": len(created_evidence)}
        )
        
        return created_evidence
    
    async def get_by_canonical_entity(
        self,
        canonical_entity_id: UUID,
    ) -> List[EntityEvidence]:
        """Get evidence records for a canonical entity.
        
        Args:
            canonical_entity_id: Canonical entity ID
            
        Returns:
            List of EntityEvidence records
        """
        stmt = select(EntityEvidence).where(
            EntityEvidence.canonical_entity_id == canonical_entity_id
        ).order_by(EntityEvidence.created_at)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_entity_mention(
        self,
        entity_mention_id: UUID,
    ) -> List[EntityEvidence]:
        """Get evidence records for an entity mention.
        
        Args:
            entity_mention_id: Entity mention ID
            
        Returns:
            List of EntityEvidence records
        """
        stmt = select(EntityEvidence).where(
            EntityEvidence.entity_mention_id == entity_mention_id
        ).order_by(EntityEvidence.created_at)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_document(
        self,
        document_id: UUID,
    ) -> List[EntityEvidence]:
        """Get evidence records for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of EntityEvidence records
        """
        stmt = select(EntityEvidence).where(
            EntityEvidence.document_id == document_id
        ).order_by(EntityEvidence.created_at)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_evidence_with_mentions_by_workflow(
        self,
        workflow_id: UUID
    ) -> List[tuple]:
        """Get evidence records with joined mention data for a workflow.

        Joins EntityEvidence with EntityMention to get source text and chunk info.
        Used for creating Evidence nodes in the knowledge graph.

        Args:
            workflow_id: Workflow UUID

        Returns:
            List of tuples: (EntityEvidence, EntityMention, CanonicalEntity)
        """
        from app.database.models import (
            EntityMention,
            CanonicalEntity,
            WorkflowEntityScope,
            DocumentChunk
        )

        stmt = (
            select(EntityEvidence, EntityMention, CanonicalEntity, DocumentChunk)
            .join(
                WorkflowEntityScope,
                EntityEvidence.canonical_entity_id == WorkflowEntityScope.canonical_entity_id
            )
            .join(EntityMention, EntityEvidence.entity_mention_id == EntityMention.id)
            .join(CanonicalEntity, EntityEvidence.canonical_entity_id == CanonicalEntity.id)
            .outerjoin(DocumentChunk, EntityMention.source_document_chunk_id == DocumentChunk.id)
            .where(WorkflowEntityScope.workflow_id == workflow_id)
            .distinct()
        )

        result = await self.session.execute(stmt)
        return result.all()

