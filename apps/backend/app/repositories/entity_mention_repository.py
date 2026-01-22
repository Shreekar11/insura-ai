"""Repository for entity mention persistence.

This repository handles persistence of document-scoped entity mentions
extracted from sections.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EntityMention
from app.repositories.base_repository import BaseRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EntityMentionRepository(BaseRepository[EntityMention]):
    """Repository for managing entity mention records.
    
    This repository provides data access methods for document-scoped
    entity mentions, including creation and querying by document/entity type.
    
    Attributes:
        session: SQLAlchemy async session for database operations
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize entity mention repository.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def create_entity_mention(
        self,
        document_id: UUID,
        entity_type: str,
        mention_text: str,
        extracted_fields: Dict[str, Any],
        section_extraction_id: Optional[UUID] = None,
        confidence: Optional[Decimal] = None,
        confidence_details: Optional[Dict[str, Any]] = None,
        source_document_chunk_id: Optional[UUID] = None,
        source_stable_chunk_id: Optional[str] = None,
    ) -> EntityMention:
        """Create a new entity mention record.
        
        Args:
            document_id: Document ID
            entity_type: Entity type (e.g., "INSURED", "CARRIER", "POLICY")
            mention_text: Original text as it appears in document
            extracted_fields: Raw mention payload from LLM extraction
            section_extraction_id: Optional section extraction ID
            confidence: Overall confidence (0.0-1.0)
            confidence_details: Detailed confidence metrics
            source_document_chunk_id: Source document chunk ID
            source_stable_chunk_id: Deterministic chunk ID
            
        Returns:
            Created EntityMention record
        """
        mention = EntityMention(
            document_id=document_id,
            entity_type=entity_type,
            mention_text=mention_text,
            extracted_fields=extracted_fields,
            section_extraction_id=section_extraction_id,
            confidence=confidence,
            confidence_details=confidence_details,
            source_document_chunk_id=source_document_chunk_id,
            source_stable_chunk_id=source_stable_chunk_id,
        )
        
        self.session.add(mention)
        await self.session.flush()
        
        LOGGER.debug(
            "Created entity mention",
            extra={
                "document_id": str(document_id),
                "entity_type": entity_type,
                "mention_id": str(mention.id),
            }
        )
        
        return mention
    
    async def create_batch(
        self,
        mentions: List[Dict[str, Any]],
    ) -> List[EntityMention]:
        """Create multiple entity mentions in batch.
        
        Args:
            mentions: List of mention dictionaries with required fields
            
        Returns:
            List of created EntityMention records
        """
        created_mentions = []
        
        for mention_data in mentions:
            mention = EntityMention(**mention_data)
            self.session.add(mention)
            created_mentions.append(mention)
        
        await self.session.flush()
        
        LOGGER.debug(
            "Created batch of entity mentions",
            extra={"count": len(created_mentions)}
        )
        
        return created_mentions
    
    async def get_by_document_id(
        self,
        document_id: UUID,
        entity_type: Optional[str] = None,
    ) -> List[EntityMention]:
        """Get entity mentions for a document.
        
        Args:
            document_id: Document ID
            entity_type: Optional entity type filter
            
        Returns:
            List of EntityMention records
        """
        stmt = select(EntityMention).where(
            EntityMention.document_id == document_id
        )
        
        if entity_type:
            stmt = stmt.where(EntityMention.entity_type == entity_type)
        
        stmt = stmt.order_by(EntityMention.created_at)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_section_extraction(
        self,
        section_extraction_id: UUID,
    ) -> List[EntityMention]:
        """Get entity mentions for a section extraction.
        
        Args:
            section_extraction_id: Section extraction ID
            
        Returns:
            List of EntityMention records
        """
        stmt = select(EntityMention).where(
            EntityMention.section_extraction_id == section_extraction_id
        ).order_by(EntityMention.created_at)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_by_id(self, mention_id: UUID) -> Optional[EntityMention]:
        """Get entity mention by ID.
        
        Args:
            mention_id: Mention ID
            
        Returns:
            EntityMention or None
        """
        stmt = select(EntityMention).where(
            EntityMention.id == mention_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

