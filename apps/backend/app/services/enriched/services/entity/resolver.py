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
    EntityEvidence,    
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
        document_id: UUID,
        workflow_id: Optional[UUID] = None
    ) -> UUID:
        """Resolve entity mention to canonical entity.
        
        Creates new canonical entity if it doesn't exist, otherwise returns
        existing entity ID. Also creates chunk-entity link if chunk_id provided.
        
        Args:
            entity_mention: Entity mention dict with entity_type, normalized_value, etc.
            chunk_id: ID of the chunk containing this mention (None for document-level entities)
            document_id: ID of the document
            workflow_id: ID of the workflow
            
        Returns:
            UUID: Canonical entity ID
        """
        entity_type = entity_mention.get("type") or entity_mention.get("entity_type")
        normalized_value = entity_mention.get("id") or entity_mention.get("normalized_value") or entity_mention.get("value")
        
        if not entity_type or not normalized_value:
            LOGGER.warning("Invalid entity mention, missing type or value", extra={"mention": entity_mention})
            raise ValueError("Entity mention must have type/entity_type and id/normalized_value")
        
        # Generate canonical key
        canonical_key = self._generate_canonical_key(entity_type, normalized_value)

        # Prepare additional attributes from entity mention
        additional_attributes = entity_mention.get("attributes", {})
        if not isinstance(additional_attributes, dict):
            additional_attributes = {}

        # Merge top-level enrichment fields that _enrich_with_rich_context sets
        merged_fields = []
        for key in ["description", "source_text", "definition_text"]:
            val = entity_mention.get(key)
            if val and key not in additional_attributes:
                additional_attributes[key] = val
                merged_fields.append(key)

        # FIX 3 VERIFICATION: Log when top-level enrichment fields are merged
        if merged_fields:
            LOGGER.debug(
                f"Top-level enrichment fields merged into additional_attributes",
                extra={
                    "entity_type": entity_type,
                    "normalized_value": normalized_value,
                    "merged_fields": merged_fields,
                    "has_description": "description" in merged_fields,
                    "has_source_text": "source_text" in merged_fields
                }
            )

        # Check if canonical entity exists
        canonical_entity = await self._get_or_create_canonical_entity(
            entity_type=entity_type,
            canonical_key=canonical_key,
            normalized_value=normalized_value,
            raw_value=entity_mention.get("raw_value", normalized_value),
            additional_attributes=additional_attributes
        )
        
        # Create entity mention (document-scoped) and evidence
        source_document_chunk_id = None
        source_stable_chunk_id = None
        
        if chunk_id is not None:
            from app.repositories.chunk_repository import ChunkRepository
            chunk_repo = ChunkRepository(self.session)
            document_chunk = await chunk_repo.get_chunk_by_id(chunk_id)
            
            if document_chunk:
                source_document_chunk_id = document_chunk.id
                source_stable_chunk_id = document_chunk.stable_chunk_id
        
        # Derive human-readable name for mention text (used in Evidence quotes)
        readable_name = (
            entity_mention.get("title")
            or entity_mention.get("coverage_name")
            or entity_mention.get("exclusion_name")
            or entity_mention.get("name")
            or entity_mention.get("term")
            or (entity_mention.get("attributes") or {}).get("coverage_name")
            or (entity_mention.get("attributes") or {}).get("title")
            or (entity_mention.get("attributes") or {}).get("exclusion_name")
            or entity_mention.get("raw_value", normalized_value)
        )

        # FIX 4 VERIFICATION: Log when readable_name differs from normalized_value (Evidence improvement)
        if readable_name != normalized_value and entity_type in ["Coverage", "Exclusion"]:
            LOGGER.debug(
                f"Human-readable mention_text derived for Evidence quote",
                extra={
                    "entity_type": entity_type,
                    "normalized_value": normalized_value,
                    "readable_name": readable_name,
                    "improves_evidence_quote": True
                }
            )

        # Create EntityMention record (document-scoped)
        mention = await self.mention_repo.create_entity_mention(
            document_id=document_id,
            entity_type=entity_type,
            mention_text=readable_name,
            extracted_fields={
                "normalized_value": normalized_value,
                "raw_value": entity_mention.get("raw_value", normalized_value),
                **{k: v for k, v in entity_mention.items() if k not in ["type", "entity_type", "id", "normalized_value", "value", "raw_value", "confidence"]}
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
        
        LOGGER.debug(
            "Resolved entity mention to canonical entity",
            extra={
                "entity_type": entity_type,
                "canonical_key": canonical_key,
                "canonical_entity_id": str(canonical_entity.id),
                "chunk_id": str(chunk_id),
                "workflow_id": str(workflow_id) if workflow_id else None
            }
        )
        
        # Add to workflow scope if provided
        if workflow_id:
            from app.repositories.entity_repository import EntityRepository
            entity_repo = EntityRepository(self.session)
            await entity_repo.add_to_workflow_scope(workflow_id, canonical_entity.id)
        
        return canonical_entity.id
    
    async def resolve_entities_batch(
        self,
        entities: list[Dict[str, Any]],
        chunk_id: Optional[UUID],
        document_id: UUID,
        workflow_id: UUID
    ) -> list[UUID]:
        """Resolve multiple entity mentions in batch.
        
        Args:
            entities: List of entity mention dicts
            chunk_id: ID of the chunk (None for document-level entities)
            document_id: ID of the document
            workflow_id: ID of the workflow
        Returns:
            list[UUID]: List of canonical entity IDs
        """
        canonical_entity_ids = []
        
        for entity in entities:
            try:
                entity_id = await self.resolve_entity(entity, chunk_id, document_id, workflow_id)
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

        Delegates to shared utility to ensure consistency with embedding system.

        Args:
            entity_type: Type of entity
            normalized_value: Normalized value

        Returns:
            str: Canonical key (hash)
        """
        from app.utils.canonical_key import generate_canonical_key
        return generate_canonical_key(entity_type, normalized_value)
    
    async def _get_or_create_canonical_entity(
        self,
        entity_type: str,
        canonical_key: str,
        normalized_value: str,
        raw_value: str,
        additional_attributes: Optional[Dict[str, Any]] = None
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
            # Merge attributes if new ones provided
            if additional_attributes:
                if not existing.attributes:
                    existing.attributes = {}
                else:
                    # Convert to dict if it's not (though it should be JSONB/dict)
                    existing.attributes = dict(existing.attributes)
                
                # Update attributes with new data
                for k, v in additional_attributes.items():
                    if v is None:
                        continue
                        
                    # Overwrite if current value is missing, None, or significantly shorter (for descriptions)
                    current_v = existing.attributes.get(k)
                    if current_v is None:
                        existing.attributes[k] = v
                    elif k in ["description", "source_text", "definition_text"] and isinstance(v, str) and isinstance(current_v, str):
                        if len(v) > len(current_v):
                            existing.attributes[k] = v
                    elif k not in existing.attributes:
                        existing.attributes[k] = v
                
                self.session.add(existing)
            return existing
        
        # Create new canonical entity
        base_attributes = {
            "normalized_value": normalized_value,
            "raw_value": raw_value
        }
        if additional_attributes:
            base_attributes.update(additional_attributes)

        canonical_entity = CanonicalEntity(
            entity_type=entity_type,
            canonical_key=canonical_key,
            attributes=base_attributes
        )
        
        self.session.add(canonical_entity)
        await self.session.flush()
        
        LOGGER.debug(
            "Created new canonical entity",
            extra={
                "entity_id": str(canonical_entity.id),
                "entity_type": entity_type,
                "canonical_key": canonical_key
            }
        )
        
        return canonical_entity

