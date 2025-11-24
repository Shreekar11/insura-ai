"""Entity resolution service for canonical entity management.

This service resolves entity mentions to canonical entities, creating new
canonical entities when needed and linking chunks to them.
"""

from typing import Dict, Any, Optional
from uuid import UUID
import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import CanonicalEntity, ChunkEntityMention, ChunkEntityLink
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EntityResolver:
    """Resolves entity mentions to canonical entities.
    
    This service manages the creation and linking of canonical entities,
    ensuring that multiple mentions of the same entity (e.g., "POL123456")
    are resolved to a single canonical entity record.
    
    Attributes:
        session: SQLAlchemy async session
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize entity resolver.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def resolve_entity(
        self,
        entity_mention: Dict[str, Any],
        chunk_id: UUID,
        document_id: UUID
    ) -> UUID:
        """Resolve entity mention to canonical entity.
        
        Creates new canonical entity if it doesn't exist, otherwise returns
        existing entity ID. Also creates chunk-entity link.
        
        Args:
            entity_mention: Entity mention dict with entity_type, normalized_value, etc.
            chunk_id: ID of the chunk containing this mention
            document_id: ID of the document
            
        Returns:
            UUID: Canonical entity ID
        """
        entity_type = entity_mention.get("entity_type")
        normalized_value = entity_mention.get("normalized_value")
        
        if not entity_type or not normalized_value:
            LOGGER.warning("Invalid entity mention, missing type or value")
            raise ValueError("Entity mention must have entity_type and normalized_value")
        
        # Generate canonical key
        canonical_key = self._generate_canonical_key(entity_type, normalized_value)
        
        # Check if canonical entity exists
        canonical_entity = await self._get_or_create_canonical_entity(
            entity_type=entity_type,
            canonical_key=canonical_key,
            normalized_value=normalized_value,
            raw_value=entity_mention.get("raw_value", normalized_value)
        )
        
        # Create chunk entity mention
        await self._create_entity_mention(
            chunk_id=chunk_id,
            canonical_entity_id=canonical_entity.id,
            entity_mention=entity_mention
        )
        
        # Create chunk-entity link
        await self._create_chunk_entity_link(
            chunk_id=chunk_id,
            canonical_entity_id=canonical_entity.id,
            confidence=entity_mention.get("confidence", 0.8)
        )
        
        LOGGER.debug(
            "Resolved entity mention to canonical entity",
            extra={
                "entity_type": entity_type,
                "canonical_key": canonical_key,
                "canonical_entity_id": str(canonical_entity.id),
                "chunk_id": str(chunk_id)
            }
        )
        
        return canonical_entity.id
    
    async def resolve_entities_batch(
        self,
        entities: list[Dict[str, Any]],
        chunk_id: UUID,
        document_id: UUID
    ) -> list[UUID]:
        """Resolve multiple entity mentions in batch.
        
        Args:
            entities: List of entity mention dicts
            chunk_id: ID of the chunk
            document_id: ID of the document
            
        Returns:
            list[UUID]: List of canonical entity IDs
        """
        canonical_entity_ids = []
        
        for entity in entities:
            try:
                entity_id = await self.resolve_entity(entity, chunk_id, document_id)
                canonical_entity_ids.append(entity_id)
            except Exception as e:
                LOGGER.error(
                    f"Failed to resolve entity: {e}",
                    extra={"entity": entity, "chunk_id": str(chunk_id)}
                )
                continue
        
        return canonical_entity_ids
    
    def _generate_canonical_key(self, entity_type: str, normalized_value: str) -> str:
        """Generate canonical key for entity.
        
        The canonical key is a hash of entity_type + normalized_value,
        ensuring uniqueness across entity types.
        
        Args:
            entity_type: Type of entity
            normalized_value: Normalized value
            
        Returns:
            str: Canonical key (hash)
        """
        # Use SHA256 hash of type:value
        key_input = f"{entity_type}:{normalized_value}".lower()
        return hashlib.sha256(key_input.encode()).hexdigest()[:32]
    
    async def _get_or_create_canonical_entity(
        self,
        entity_type: str,
        canonical_key: str,
        normalized_value: str,
        raw_value: str
    ) -> CanonicalEntity:
        """Get existing or create new canonical entity.
        
        Args:
            entity_type: Type of entity
            canonical_key: Canonical key
            normalized_value: Normalized value
            raw_value: Raw value
            
        Returns:
            CanonicalEntity: The canonical entity
        """
        # Try to find existing entity
        query = select(CanonicalEntity).where(
            CanonicalEntity.entity_type == entity_type,
            CanonicalEntity.canonical_key == canonical_key
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            LOGGER.debug(f"Found existing canonical entity: {existing.id}")
            return existing
        
        # Create new canonical entity
        canonical_entity = CanonicalEntity(
            entity_type=entity_type,
            canonical_key=canonical_key,
            canonical_value=normalized_value,
            first_seen_value=raw_value,
            metadata={}
        )
        
        self.session.add(canonical_entity)
        await self.session.flush()
        
        LOGGER.info(
            "Created new canonical entity",
            extra={
                "entity_id": str(canonical_entity.id),
                "entity_type": entity_type,
                "canonical_key": canonical_key
            }
        )
        
        return canonical_entity
    
    async def _create_entity_mention(
        self,
        chunk_id: UUID,
        canonical_entity_id: UUID,
        entity_mention: Dict[str, Any]
    ) -> ChunkEntityMention:
        """Create chunk entity mention record.
        
        Args:
            chunk_id: Chunk ID
            canonical_entity_id: Canonical entity ID
            entity_mention: Entity mention data
            
        Returns:
            ChunkEntityMention: Created mention record
        """
        mention = ChunkEntityMention(
            chunk_id=chunk_id,
            canonical_entity_id=canonical_entity_id,
            entity_type=entity_mention.get("entity_type"),
            raw_value=entity_mention.get("raw_value"),
            normalized_value=entity_mention.get("normalized_value"),
            confidence=entity_mention.get("confidence", 0.8),
            span_start=entity_mention.get("span_start"),
            span_end=entity_mention.get("span_end")
        )
        
        self.session.add(mention)
        await self.session.flush()
        
        return mention
    
    async def _create_chunk_entity_link(
        self,
        chunk_id: UUID,
        canonical_entity_id: UUID,
        confidence: float
    ) -> ChunkEntityLink:
        """Create chunk-entity link.
        
        Args:
            chunk_id: Chunk ID
            canonical_entity_id: Canonical entity ID
            confidence: Confidence score
            
        Returns:
            ChunkEntityLink: Created link record
        """
        # Check if link already exists
        query = select(ChunkEntityLink).where(
            ChunkEntityLink.chunk_id == chunk_id,
            ChunkEntityLink.canonical_entity_id == canonical_entity_id
        )
        result = await self.session.execute(query)
        existing_link = result.scalar_one_or_none()
        
        if existing_link:
            # Update confidence if higher
            if confidence > existing_link.confidence:
                existing_link.confidence = confidence
                await self.session.flush()
            return existing_link
        
        # Create new link
        link = ChunkEntityLink(
            chunk_id=chunk_id,
            canonical_entity_id=canonical_entity_id,
            confidence=confidence
        )
        
        self.session.add(link)
        await self.session.flush()
        
        return link
