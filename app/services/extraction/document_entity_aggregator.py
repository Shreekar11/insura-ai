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

from app.database.models import NormalizedChunk
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


class DocumentEntityAggregator:
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
        
        LOGGER.info("Initialized DocumentEntityAggregator")
    
    async def aggregate_entities(
        self,
        document_id: UUID
    ) -> AggregatedEntities:
        """Aggregate entities from all chunks of a document.
        
        Args:
            document_id: Document ID to aggregate entities for
            
        Returns:
            AggregatedEntities: Aggregated and deduplicated entities
        """
        LOGGER.info(
            f"Starting entity aggregation for document",
            extra={"document_id": str(document_id)}
        )
        
        # Fetch all normalized chunks for the document
        chunks = await self._fetch_normalized_chunks(document_id)
        
        if not chunks:
            LOGGER.warning(
                f"No normalized chunks found for document",
                extra={"document_id": str(document_id)}
            )
            return AggregatedEntities(
                entities=[],
                chunk_entity_map=[],
                total_chunks=0,
                total_entities=0,
                unique_entities=0
            )
        
        # Extract and aggregate entities
        all_entities = []
        chunk_mappings = []
        
        for chunk in chunks:
            entities = chunk.entities or []
            
            if entities:
                # Track which entities came from which chunk
                entity_ids = [e.get("entity_id") for e in entities if e.get("entity_id")]
                chunk_mappings.append(ChunkEntityMapping(
                    chunk_id=chunk.id,
                    entity_ids=entity_ids
                ))
                
                # Add chunk_id to each entity for tracking
                for entity in entities:
                    entity["source_chunk_id"] = str(chunk.id)
                    all_entities.append(entity)
        
        # Deduplicate entities
        unique_entities = self._deduplicate_entities(all_entities)
        
        result = AggregatedEntities(
            entities=unique_entities,
            chunk_entity_map=chunk_mappings,
            total_chunks=len(chunks),
            total_entities=len(all_entities),
            unique_entities=len(unique_entities)
        )
        
        LOGGER.info(
            f"Entity aggregation completed",
            extra={
                "document_id": str(document_id),
                "total_chunks": result.total_chunks,
                "total_entities": result.total_entities,
                "unique_entities": result.unique_entities,
                "deduplication_ratio": f"{(1 - result.unique_entities / max(result.total_entities, 1)) * 100:.1f}%"
            }
        )
        
        return result
    
    async def _fetch_normalized_chunks(
        self,
        document_id: UUID
    ) -> List[NormalizedChunk]:
        """Fetch all normalized chunks for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of normalized chunks
        """
        from app.database.models import DocumentChunk
        
        stmt = (
            select(NormalizedChunk)
            .join(NormalizedChunk.chunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(stmt)
        chunks = result.scalars().all()
        
        LOGGER.debug(
            f"Fetched {len(chunks)} normalized chunks",
            extra={"document_id": str(document_id)}
        )
        
        return list(chunks)
    
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
                # If no entity_id, generate one
                entity_id = self._generate_entity_id(
                    entity.get("entity_type", "UNKNOWN"),
                    entity.get("normalized_value", "")
                )
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
                        "entity_type": best_entity.get("entity_type"),
                        "normalized_value": best_entity.get("normalized_value"),
                        "kept_confidence": best_entity.get("confidence")
                    }
                )
        
        return unique_entities
    
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
