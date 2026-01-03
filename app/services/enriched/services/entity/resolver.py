"""Entity resolution service for canonical entity management.

This service resolves entity mentions to canonical entities, creating new
canonical entities when needed and linking chunks to them.
"""

from typing import Dict, Any, Optional
from uuid import UUID
import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    CanonicalEntity,
    ChunkEntityMention,
    ChunkEntityLink,
    EntityMention,
    EntityEvidence,
    InsuredEntity,
    CarrierEntity,
    PolicyEntity,
    ClaimEntity,
)
from app.repositories.entity_mention_repository import EntityMentionRepository
from app.repositories.entity_evidence_repository import EntityEvidenceRepository
from app.utils.logging import get_logger
from decimal import Decimal

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
        self.mention_repo = EntityMentionRepository(session)
        self.evidence_repo = EntityEvidenceRepository(session)
    
    async def resolve_entity(
        self,
        entity_mention: Dict[str, Any],
        chunk_id: Optional[UUID],
        document_id: UUID
    ) -> UUID:
        """Resolve entity mention to canonical entity.
        
        Creates new canonical entity if it doesn't exist, otherwise returns
        existing entity ID. Also creates chunk-entity link if chunk_id provided.
        
        Args:
            entity_mention: Entity mention dict with entity_type, normalized_value, etc.
            chunk_id: ID of the chunk containing this mention (None for document-level entities)
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
        
        # Create entity mention (document-scoped) and evidence
        # Note: chunk_id can be None for document-level entities
        # chunk_id should be a document_chunk.id (not normalized_chunk.id)
        source_document_chunk_id = None
        source_stable_chunk_id = None
        
        if chunk_id is not None:
            # Try to fetch as DocumentChunk first (preferred - current flow)
            from app.database.models import DocumentChunk
            stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
            result = await self.session.execute(stmt)
            document_chunk = result.scalar_one_or_none()
            
            if document_chunk:
                source_document_chunk_id = document_chunk.id
                source_stable_chunk_id = document_chunk.stable_chunk_id
            else:
                # Fallback: Try as normalized_chunk.id (legacy compatibility)
                from app.database.models import NormalizedChunk
                stmt = select(NormalizedChunk).where(NormalizedChunk.id == chunk_id)
                result = await self.session.execute(stmt)
                normalized_chunk = result.scalar_one_or_none()
                
                if normalized_chunk and normalized_chunk.chunk:
                    source_document_chunk_id = normalized_chunk.chunk.id
                    source_stable_chunk_id = normalized_chunk.chunk.stable_chunk_id
                    LOGGER.debug(
                        "Using legacy normalized_chunk path",
                        extra={"normalized_chunk_id": str(chunk_id), "document_chunk_id": str(source_document_chunk_id)}
                    )
        
        # Create EntityMention record (document-scoped)
        mention = await self.mention_repo.create_entity_mention(
            document_id=document_id,
            entity_type=entity_type,
            mention_text=entity_mention.get("raw_value", normalized_value),
            extracted_fields={
                "normalized_value": normalized_value,
                "raw_value": entity_mention.get("raw_value", normalized_value),
                **{k: v for k, v in entity_mention.items() if k not in ["entity_type", "normalized_value", "raw_value", "confidence"]}
            },
            confidence=Decimal(str(entity_mention.get("confidence", 0.8))),
            source_document_chunk_id=source_document_chunk_id,
            source_stable_chunk_id=source_stable_chunk_id,
        )
        
        # Create EntityEvidence record linking canonical entity to mention
        await self.evidence_repo.create_entity_evidence(
            canonical_entity_id=canonical_entity.id,
            entity_mention_id=mention.id,
            document_id=document_id,
            confidence=Decimal(str(entity_mention.get("confidence", 0.8))),
            evidence_type="extracted",
        )
        
        # Create typed canonical entity record if applicable
        await self._create_typed_canonical_entity(
            canonical_entity=canonical_entity,
            entity_mention=entity_mention,
        )
        
        # Legacy: Also create ChunkEntityMention and ChunkEntityLink for backward compatibility
        # Only create if chunk_id is a normalized_chunk.id (legacy path)
        # Since we're not creating normalized_chunks anymore, skip if it's a document_chunk.id
        if chunk_id is not None:
            # Check if this is a normalized_chunk.id (legacy)
            from app.database.models import NormalizedChunk
            stmt = select(NormalizedChunk).where(NormalizedChunk.id == chunk_id)
            result = await self.session.execute(stmt)
            normalized_chunk = result.scalar_one_or_none()
            
            if normalized_chunk:
                # Only create legacy records if chunk_id is actually a normalized_chunk.id
                await self._create_legacy_chunk_entity_mention(
                    chunk_id=chunk_id,
                    canonical_entity_id=canonical_entity.id,
                    entity_mention=entity_mention
                )
                
                await self._create_chunk_entity_link(
                    chunk_id=chunk_id,
                    canonical_entity_id=canonical_entity.id,
                    confidence=entity_mention.get("confidence", 0.8)
                )
                LOGGER.debug(
                    "Created legacy ChunkEntityMention and ChunkEntityLink for normalized_chunk",
                    extra={"normalized_chunk_id": str(chunk_id)}
                )
            else:
                LOGGER.debug(
                    "Skipping legacy record creation - chunk_id is not a normalized_chunk.id",
                    extra={"chunk_id": str(chunk_id)}
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
        chunk_id: Optional[UUID],
        document_id: UUID
    ) -> list[UUID]:
        """Resolve multiple entity mentions in batch.
        
        Args:
            entities: List of entity mention dicts
            chunk_id: ID of the chunk (None for document-level entities)
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
            attributes={
                "normalized_value": normalized_value,
                "raw_value": raw_value
            }
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
    
    async def _create_typed_canonical_entity(
        self,
        canonical_entity: CanonicalEntity,
        entity_mention: Dict[str, Any],
    ) -> None:
        """Create typed canonical entity record if applicable.
        
        Args:
            canonical_entity: Canonical entity
            entity_mention: Entity mention data
        """
        entity_type = canonical_entity.entity_type.upper()
        normalized_value = entity_mention.get("normalized_value", "")
        attributes = entity_mention.get("attributes", {})
        confidence = Decimal(str(entity_mention.get("confidence", 0.8)))
        
        try:
            if entity_type == "INSURED":
                # Check if InsuredEntity already exists
                stmt = select(InsuredEntity).where(InsuredEntity.id == canonical_entity.id)
                result = await self.session.execute(stmt)
                if result.scalar_one_or_none() is None:
                    insured = InsuredEntity(
                        id=canonical_entity.id,
                        canonical_name=normalized_value,
                        normalized_name=normalized_value.lower().strip(),
                        primary_address=attributes.get("address"),
                        confidence=confidence,
                    )
                    self.session.add(insured)
                    await self.session.flush()
                    LOGGER.debug(f"Created InsuredEntity for {canonical_entity.id}")
                    
            elif entity_type == "CARRIER":
                stmt = select(CarrierEntity).where(CarrierEntity.id == canonical_entity.id)
                result = await self.session.execute(stmt)
                if result.scalar_one_or_none() is None:
                    carrier = CarrierEntity(
                        id=canonical_entity.id,
                        canonical_name=normalized_value,
                        normalized_name=normalized_value.lower().strip(),
                        naic=attributes.get("naic"),
                        confidence=confidence,
                    )
                    self.session.add(carrier)
                    await self.session.flush()
                    LOGGER.debug(f"Created CarrierEntity for {canonical_entity.id}")
                    
            elif entity_type == "POLICY":
                stmt = select(PolicyEntity).where(PolicyEntity.id == canonical_entity.id)
                result = await self.session.execute(stmt)
                if result.scalar_one_or_none() is None:
                    from datetime import datetime as dt
                    policy = PolicyEntity(
                        id=canonical_entity.id,
                        policy_number=normalized_value,
                        effective_date=attributes.get("effective_date"),
                        expiration_date=attributes.get("expiration_date"),
                        confidence=confidence,
                    )
                    self.session.add(policy)
                    await self.session.flush()
                    LOGGER.debug(f"Created PolicyEntity for {canonical_entity.id}")
                    
            elif entity_type == "CLAIM":
                stmt = select(ClaimEntity).where(ClaimEntity.id == canonical_entity.id)
                result = await self.session.execute(stmt)
                if result.scalar_one_or_none() is None:
                    claim = ClaimEntity(
                        id=canonical_entity.id,
                        claim_number=normalized_value,
                        loss_date=attributes.get("loss_date"),
                        confidence=confidence,
                    )
                    self.session.add(claim)
                    await self.session.flush()
                    LOGGER.debug(f"Created ClaimEntity for {canonical_entity.id}")
                    
        except Exception as e:
            LOGGER.warning(
                f"Failed to create typed canonical entity: {e}",
                exc_info=True,
                extra={"entity_type": entity_type, "canonical_entity_id": str(canonical_entity.id)}
            )
    
    async def _create_legacy_chunk_entity_mention(
        self,
        chunk_id: UUID,
        canonical_entity_id: UUID,
        entity_mention: Dict[str, Any]
    ) -> ChunkEntityMention:
        """Create legacy chunk entity mention record (for backward compatibility).
        
        Args:
            chunk_id: Chunk ID (normalized_chunk.id)
            canonical_entity_id: Canonical entity ID
            entity_mention: Entity mention data
            
        Returns:
            ChunkEntityMention: Created mention record
        """
        mention = ChunkEntityMention(
            chunk_id=chunk_id,
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
