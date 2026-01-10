"""Document entity aggregator service.

This service aggregates entities from all chunks of a document and performs
deduplication to prepare for canonical entity resolution.
"""

import hashlib
from typing import List, Dict, Any, Optional
from uuid import UUID
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EntityMention
from app.services.enriched.services.entity.entity_synthesizer import EntitySynthesizer
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class ChunkEntityMapping:
    """Maps a chunk to its entities."""
    chunk_id: UUID
    entity_ids: List[str]  # List of entity_id values from the chunk


@dataclass
class AggregatedEntities:
    """Result of entity aggregation across all chunks."""
    entities: List[Dict[str, Any]]  # Unique entities
    chunk_entity_map: List[ChunkEntityMapping]  # Chunk → Entity links
    total_chunks: int
    total_entities: int
    unique_entities: int


class EntityAggregator:
    """Aggregates entities from all chunks of a document.
    
    This service:
    1. Fetches all normalized chunks for a document
    2. Extracts entities from each chunk
    3. Deduplicates entities based on (entity_type, normalized_value)
    4. Builds chunk-to-entity mapping for later resolution
    
    Attributes:
        session: Database session
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize aggregator.
        
        Args:
            session: Database session
        """
        self.session = session
        self.section_extraction_repo = SectionExtractionRepository(session)
        self.synthesizer = EntitySynthesizer()
        
        LOGGER.info("Initialized EntityAggregator")
    
    async def aggregate_entities(
        self,
        document_id: UUID,
        workflow_id: UUID
    ) -> AggregatedEntities:
        """Aggregate entities from all chunks of a document.
        
        Args:
            document_id: Document ID to aggregate entities
            workflow_id: Workflow ID
            
        Returns:
            AggregatedEntities: Aggregated and deduplicated entities
        """
        LOGGER.info(
            f"Starting entity aggregation for document",
            extra={"document_id": str(document_id), "workflow_id": str(workflow_id)}
        )
        
        # Strategy 1: Try fetching from entity_mentions
        entity_mentions = await self._fetch_entity_mentions(document_id)
        
        if entity_mentions:
            LOGGER.info(
                f"Found {len(entity_mentions)} entity mentions, using entity_mentions table",
                extra={"document_id": str(document_id)}
            )
            all_entities = []
            chunk_mappings = []
            
            for mention in entity_mentions:
                # Extract entity data from mention
                extracted_fields = mention.extracted_fields or {}
                entity = {
                    "entity_type": mention.entity_type,
                    "normalized_value": extracted_fields.get("normalized_value", mention.mention_text),
                    "raw_value": mention.mention_text,
                    "confidence": float(mention.confidence) if mention.confidence else 0.8,
                    "source_chunk_id": str(mention.source_document_chunk_id) if mention.source_document_chunk_id else None,
                    "source_stable_chunk_id": mention.source_stable_chunk_id,
                    **extracted_fields
                }
                
                # Generate entity_id if not present
                if "entity_id" not in entity:
                    entity["entity_id"] = self._generate_entity_id(
                        entity["entity_type"],
                        entity["normalized_value"]
                    )
                
                all_entities.append(entity)
                
                if mention.source_document_chunk_id:
                    chunk_mappings.append(ChunkEntityMapping(
                        chunk_id=mention.source_document_chunk_id,
                        entity_ids=[entity["entity_id"]]
                    ))
        
        else:
            # Strategy 2: Fallback to section_extractions
            LOGGER.info(
                f"No entity mentions found, falling back to section_extractions",
                extra={"document_id": str(document_id)}
            )
            section_extractions = await self.section_extraction_repo.get_by_document(document_id)
            
            chunks = None

            # Extract from section_extractions
            all_entities = []
            chunk_mappings = []
            
            # Collect unique chunk IDs from section extractions for chunk count
            chunk_id_set = set()
            
            for extraction in section_extractions:
                extracted_fields = extraction.extracted_fields or {}
                entities = extracted_fields.get("entities")
                
                # If entities field is missing or empty, try synthesizing from structured data
                if not entities:
                    entities = self.synthesizer.synthesize_entities_from_data(extracted_fields, extraction.section_type)
                
                LOGGER.debug(
                    f"Checking section extraction for entities",
                    extra={
                        "document_id": str(document_id),
                        "section_type": extraction.section_type,
                        "section_extraction_id": str(extraction.id),
                        "entities_found": len(entities) if entities else 0,
                        "extracted_fields_keys": list(extracted_fields.keys())
                    }
                )
                
                if entities:
                    source_chunks = extraction.source_chunks or {}
                    chunk_ids = source_chunks.get("chunk_ids", [])
                    stable_chunk_ids = source_chunks.get("stable_chunk_ids", [])
                    
                    normalized_count = 0
                    for entity in entities:
                        # Normalize entity format to match resolver expectations
                        normalized_entity = self._normalize_entity_format(entity)
                        
                        if not normalized_entity:
                            LOGGER.warning(
                                f"Entity missing required fields, skipping",
                                extra={
                                    "entity": entity,
                                    "section_extraction_id": str(extraction.id),
                                    "section_type": extraction.section_type
                                }
                            )
                            continue
                        
                        normalized_entity["source_section_extraction_id"] = str(extraction.id)
                        if stable_chunk_ids:
                            normalized_entity["source_stable_chunk_id"] = stable_chunk_ids[0] if stable_chunk_ids else None
                        
                        all_entities.append(normalized_entity)
                        normalized_count += 1
                    
                    LOGGER.debug(
                        f"Normalized {normalized_count} entities from section_extractions",
                        extra={
                            "document_id": str(document_id),
                            "section_type": extraction.section_type,
                            "section_extraction_id": str(extraction.id),
                            "total_entities": len(entities),
                            "normalized_count": normalized_count
                        }
                    )
                    
                    # Create chunk mappings from source_chunks
                    for chunk_id_str in chunk_ids:
                        try:
                            chunk_id = UUID(chunk_id_str) if isinstance(chunk_id_str, str) else chunk_id_str
                            chunk_id_set.add(chunk_id)
                            entity_ids = [e.get("entity_id") for e in entities if e.get("entity_id")]
                            chunk_mappings.append(ChunkEntityMapping(
                                chunk_id=chunk_id,
                                entity_ids=entity_ids
                            ))
                        except (ValueError, TypeError):
                            continue
            
            # Create placeholder chunks list for coverage metrics (only count matters)
            chunks = [None] * len(chunk_id_set) if chunk_id_set else []
        
        # Deduplicate entities
        unique_entities = self._deduplicate_entities(all_entities)
                
        # Calculate total chunks - use chunk_mappings count if chunks is None
        total_chunks = len(chunks) if chunks is not None else len(set(m.chunk_id for m in chunk_mappings))
        
        result = AggregatedEntities(
            entities=unique_entities,
            chunk_entity_map=chunk_mappings,
            total_chunks=total_chunks,
            total_entities=len(all_entities),
            unique_entities=len(unique_entities),
        )
        
        LOGGER.info(
            f"Entity aggregation completed",
            extra={
                "document_id": str(document_id),
                "total_chunks": result.total_chunks,
                "total_entities": result.total_entities,
                "unique_entities": result.unique_entities,
                "deduplication_ratio": f"{(1 - result.unique_entities / max(result.total_entities, 1)) * 100:.1f}%",
            }
        )
        
        return result
    
    async def _fetch_entity_mentions(
        self,
        document_id: UUID
    ) -> List[EntityMention]:
        """Fetch entity mentions for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of entity mentions
        """
        stmt = select(EntityMention).where(
            EntityMention.document_id == document_id
        ).order_by(EntityMention.created_at)
        
        result = await self.session.execute(stmt)
        mentions = result.scalars().all()
        
        LOGGER.debug(
            f"Fetched {len(mentions)} entity mentions",
            extra={"document_id": str(document_id)}
        )
        
        return list(mentions)
    
    def _deduplicate_entities(
        self,
        entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Deduplicate entities based on entity_id.
        
        The entity_id is generated by the LLM based on entity_type and normalized_value,
        so entities with the same entity_id are duplicates.
        
        When duplicates are found, we keep the one with highest confidence.
        
        Args:
            entities: List of entities to deduplicate
            
        Returns:
            List of unique entities
        """
        if not entities:
            return []
        
        # Group by entity_id
        entity_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        for entity in entities:
            entity_id = entity.get("entity_id")
            if not entity_id:
                # If no entity_id, generate one (handle both formats)
                entity_type = entity.get("entity_type") or entity.get("type") or "UNKNOWN"
                normalized_value = entity.get("normalized_value") or entity.get("value") or ""
                entity_id = self._generate_entity_id(entity_type, normalized_value)
                entity["entity_id"] = entity_id
            
            if entity_id not in entity_groups:
                entity_groups[entity_id] = []
            entity_groups[entity_id].append(entity)
        
        # For each group, keep the entity with highest confidence
        unique_entities = []
        
        for entity_id, group in entity_groups.items():
            if len(group) == 1:
                unique_entities.append(group[0])
            else:
                # Multiple entities with same ID - keep highest confidence
                best_entity = max(group, key=lambda e: e.get("confidence", 0.0))
                
                # Merge source_chunk_ids from all duplicates
                source_chunks = set()
                for entity in group:
                    if "source_chunk_id" in entity:
                        source_chunks.add(entity["source_chunk_id"])
                
                best_entity["source_chunk_ids"] = list(source_chunks)
                unique_entities.append(best_entity)
                
                LOGGER.debug(
                    f"Deduplicated {len(group)} entities with ID {entity_id}",
                    extra={
                        "entity_type": best_entity.get("entity_type") or best_entity.get("type"),
                        "normalized_value": best_entity.get("normalized_value") or best_entity.get("value"),
                        "kept_confidence": best_entity.get("confidence"),
                        "dropped_count": len(group) - 1
                    }
                )
        
        LOGGER.debug(
            f"Deduplication complete: {len(entities)} → {len(unique_entities)} entities",
            extra={
                "original_count": len(entities),
                "unique_count": len(unique_entities),
                "duplicates_removed": len(entities) - len(unique_entities)
            }
        )
        
        return unique_entities
    
    def _normalize_entity_format(
        self,
        entity: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Normalize entity format to match resolver expectations.
        
        Converts from extraction format (type/id/attributes) to resolver format
        (entity_type/normalized_value/raw_value).
        
        Args:
            entity: Entity dict in either format
            
        Returns:
            Normalized entity dict, or None if required fields missing
        """
        # Extract entity type (support both formats)
        entity_type = entity.get("type") or entity.get("entity_type")
        if not entity_type:
            return None
        
        # Extract normalized value / ID
        normalized_value = entity.get("id") or entity.get("normalized_value") or entity.get("value")
        if not normalized_value:
            return None
        
        # Extract raw value
        raw_value = entity.get("raw_value") or entity.get("value") or entity.get("normalized_value") or normalized_value
        
        # Build normalized entity dict
        normalized_entity = {
            "entity_type": entity_type,
            "normalized_value": normalized_value,
            "raw_value": raw_value,
            "confidence": entity.get("confidence", 0.8),
        }
        
        # Preserve other fields (id/entity_id, span_start, span_end, attributes, etc.)
        for key, value in entity.items():
            if key not in ["type", "value", "entity_type", "normalized_value", "raw_value", "confidence"]:
                normalized_entity[key] = value
        
        # Support attributes block directly
        if "attributes" in entity and isinstance(entity["attributes"], dict):
            normalized_entity.update(entity["attributes"])
        
        # Generate entity_id if not present
        if "entity_id" not in normalized_entity:
            normalized_entity["entity_id"] = self._generate_entity_id(
                normalized_entity["entity_type"],
                normalized_entity["normalized_value"]
            )
        
        return normalized_entity
    
    def _generate_entity_id(
        self,
        entity_type: str,
        normalized_value: str
    ) -> str:
        """Generate deterministic entity ID.
        
        Args:
            entity_type: Entity type
            normalized_value: Normalized value
            
        Returns:
            Entity ID (lowercase with underscores)
        """
        # Create a simple deterministic ID
        key = f"{entity_type}:{normalized_value}".lower()
        # Use first 16 chars of SHA1 hash for shorter IDs
        hash_hex = hashlib.sha1(key.encode()).hexdigest()[:16]
        return f"{entity_type.lower()}_{hash_hex}"

