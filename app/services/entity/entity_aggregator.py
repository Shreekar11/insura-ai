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

from app.database.models import NormalizedChunk, SectionExtraction, EntityMention
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Required entity types for minimum coverage
REQUIRED_ENTITY_TYPES = {"POLICY_NUMBER", "INSURED_NAME"}


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
    coverage_metrics: Optional['EntityCoverageMetrics'] = None


@dataclass
class EntityCoverageMetrics:
    """Metrics tracking entity coverage and quality."""
    total_mentions: int
    unique_entities: int
    mentions_by_type: Dict[str, int]
    dropped_mentions: List[Dict[str, Any]]
    coverage_status: Dict[str, bool]  # e.g., {"POLICY_NUMBER": True, "INSURED_NAME": False}
    missing_required_types: List[str]
    fallback_applied: bool = False
    fallback_entities: List[Dict[str, Any]] = None


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
        
        LOGGER.info("Initialized EntityAggregator")
    
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
        
        # Strategy 1: Try fetching from entity_mentions (preferred - doc-aligned)
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
            
            if not section_extractions:
                # Strategy 3: Final fallback to normalized_chunks (legacy)
                LOGGER.warning(
                    f"No section extractions found, falling back to normalized_chunks (legacy)",
                    extra={"document_id": str(document_id)}
                )
                chunks = await self._fetch_normalized_chunks(document_id)
                
                if not chunks:
                    LOGGER.warning(
                        f"No data sources found for entity aggregation",
                        extra={"document_id": str(document_id)}
                    )
                    return AggregatedEntities(
                        entities=[],
                        chunk_entity_map=[],
                        total_chunks=0,
                        total_entities=0,
                        unique_entities=0
                    )
                
                # Extract from normalized_chunks (legacy path)
                all_entities = []
                chunk_mappings = []
                
                for chunk in chunks:
                    entities = chunk.entities or []
                    
                    if entities:
                        entity_ids = [e.get("entity_id") for e in entities if e.get("entity_id")]
                        chunk_mappings.append(ChunkEntityMapping(
                            chunk_id=chunk.id,
                            entity_ids=entity_ids
                        ))
                        
                        for entity in entities:
                            entity["source_chunk_id"] = str(chunk.id)
                            all_entities.append(entity)
            else:
                # Extract from section_extractions
                all_entities = []
                chunk_mappings = []
                
                for extraction in section_extractions:
                    extracted_fields = extraction.extracted_fields or {}
                    entities = extracted_fields.get("entities", [])
                    
                    if entities:
                        source_chunks = extraction.source_chunks or {}
                        chunk_ids = source_chunks.get("chunk_ids", [])
                        stable_chunk_ids = source_chunks.get("stable_chunk_ids", [])
                        
                        for entity in entities:
                            entity["source_section_extraction_id"] = str(extraction.id)
                            if stable_chunk_ids:
                                entity["source_stable_chunk_id"] = stable_chunk_ids[0] if stable_chunk_ids else None
                            all_entities.append(entity)
                        
                        # Create chunk mappings from source_chunks
                        for chunk_id_str in chunk_ids:
                            try:
                                chunk_id = UUID(chunk_id_str) if isinstance(chunk_id_str, str) else chunk_id_str
                                entity_ids = [e.get("entity_id") for e in entities if e.get("entity_id")]
                                chunk_mappings.append(ChunkEntityMapping(
                                    chunk_id=chunk_id,
                                    entity_ids=entity_ids
                                ))
                            except (ValueError, TypeError):
                                continue
        
        # Deduplicate entities
        unique_entities = self._deduplicate_entities(all_entities)
        
        # Check minimum coverage and apply fallbacks if needed
        coverage_metrics = self._check_minimum_coverage(
            unique_entities=unique_entities,
            all_chunk_entities=all_entities,
            chunks=chunks
        )
        
        # Apply fallback heuristics if required entities are missing
        if coverage_metrics.missing_required_types:
            LOGGER.warning(
                f"Missing required entity types: {coverage_metrics.missing_required_types}",
                extra={
                    "document_id": str(document_id),
                    "missing_types": coverage_metrics.missing_required_types
                }
            )
            
            fallback_entities = self._apply_fallback_heuristics(
                unique_entities=unique_entities,
                all_chunk_entities=all_entities,
                missing_types=coverage_metrics.missing_required_types
            )
            
            if fallback_entities:
                unique_entities.extend(fallback_entities)
                coverage_metrics.fallback_applied = True
                coverage_metrics.fallback_entities = fallback_entities
                
                LOGGER.info(
                    f"Applied fallback heuristics, added {len(fallback_entities)} entities",
                    extra={
                        "document_id": str(document_id),
                        "fallback_count": len(fallback_entities),
                        "entity_types": [e.get("entity_type") for e in fallback_entities]
                    }
                )
        
        result = AggregatedEntities(
            entities=unique_entities,
            chunk_entity_map=chunk_mappings,
            total_chunks=len(chunks),
            total_entities=len(all_entities),
            unique_entities=len(unique_entities),
            coverage_metrics=coverage_metrics
        )
        
        LOGGER.info(
            f"Entity aggregation completed",
            extra={
                "document_id": str(document_id),
                "total_chunks": result.total_chunks,
                "total_entities": result.total_entities,
                "unique_entities": result.unique_entities,
                "deduplication_ratio": f"{(1 - result.unique_entities / max(result.total_entities, 1)) * 100:.1f}%",
                "coverage_status": coverage_metrics.coverage_status,
                "fallback_applied": coverage_metrics.fallback_applied
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
    
    async def _fetch_normalized_chunks(
        self,
        document_id: UUID
    ) -> List[NormalizedChunk]:
        """Fetch all normalized chunks for a document (legacy fallback).
        
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
            f"Fetched {len(chunks)} normalized chunks (legacy)",
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
    
    def _check_minimum_coverage(
        self,
        unique_entities: List[Dict[str, Any]],
        all_chunk_entities: List[Dict[str, Any]],
        chunks: List[NormalizedChunk]
    ) -> EntityCoverageMetrics:
        """Check if minimum required entities are present.
        
        Args:
            unique_entities: Deduplicated entities
            all_chunk_entities: All entities before deduplication
            chunks: Document chunks
            
        Returns:
            EntityCoverageMetrics with coverage status and diagnostics
        """
        # Count mentions by type
        mentions_by_type = {}
        for entity in all_chunk_entities:
            entity_type = entity.get("entity_type", "UNKNOWN")
            mentions_by_type[entity_type] = mentions_by_type.get(entity_type, 0) + 1
        
        # Check coverage for required types
        coverage_status = {}
        missing_required_types = []
        
        for required_type in REQUIRED_ENTITY_TYPES:
            has_entity = any(
                e.get("entity_type") == required_type 
                for e in unique_entities
            )
            coverage_status[required_type] = has_entity
            
            if not has_entity:
                missing_required_types.append(required_type)
        
        # Track dropped mentions (entities that didn't make it through deduplication)
        dropped_mentions = []
        unique_entity_ids = {e.get("entity_id") for e in unique_entities}
        
        for entity in all_chunk_entities:
            if entity.get("entity_id") not in unique_entity_ids:
                dropped_mentions.append({
                    "entity_type": entity.get("entity_type"),
                    "normalized_value": entity.get("normalized_value"),
                    "confidence": entity.get("confidence"),
                    "reason": "deduplication"
                })
        
        metrics = EntityCoverageMetrics(
            total_mentions=len(all_chunk_entities),
            unique_entities=len(unique_entities),
            mentions_by_type=mentions_by_type,
            dropped_mentions=dropped_mentions,
            coverage_status=coverage_status,
            missing_required_types=missing_required_types
        )
        
        # Log detailed coverage report
        LOGGER.info(
            "Entity coverage check completed",
            extra={
                "total_mentions": metrics.total_mentions,
                "unique_entities": metrics.unique_entities,
                "mentions_by_type": metrics.mentions_by_type,
                "coverage_status": metrics.coverage_status,
                "missing_required": metrics.missing_required_types,
                "dropped_count": len(metrics.dropped_mentions)
            }
        )
        
        return metrics
    
    def _apply_fallback_heuristics(
        self,
        unique_entities: List[Dict[str, Any]],
        all_chunk_entities: List[Dict[str, Any]],
        missing_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Apply fallback heuristics to promote missing required entities.
        
        Strategy:
        1. For each missing type, find all chunk-level mentions
        2. Pick the highest-confidence mention
        3. Promote it to unique entities even if it was deduplicated
        
        Args:
            unique_entities: Current unique entities
            all_chunk_entities: All chunk entities
            missing_types: List of missing required entity types
            
        Returns:
            List of fallback entities to add
        """
        fallback_entities = []
        
        for missing_type in missing_types:
            # Find all mentions of this type
            type_mentions = [
                e for e in all_chunk_entities
                if e.get("entity_type") == missing_type
            ]
            
            if not type_mentions:
                LOGGER.warning(
                    f"No mentions found for required type {missing_type}, cannot apply fallback"
                )
                continue
            
            # Pick highest confidence mention
            best_mention = max(type_mentions, key=lambda e: e.get("confidence", 0.0))
            
            # Check if it's already in unique entities (shouldn't be, but defensive)
            if any(e.get("entity_id") == best_mention.get("entity_id") for e in unique_entities):
                LOGGER.debug(
                    f"Best mention for {missing_type} already in unique entities"
                )
                continue
            
            # Add to fallback list
            fallback_entities.append(best_mention)
            
            LOGGER.info(
                f"Fallback heuristic: promoting {missing_type}",
                extra={
                    "entity_type": missing_type,
                    "normalized_value": best_mention.get("normalized_value"),
                    "confidence": best_mention.get("confidence"),
                    "source_chunk_id": best_mention.get("source_chunk_id")
                }
            )
        
        return fallback_entities
    
    def get_coverage_report(self, aggregated: AggregatedEntities) -> Dict[str, Any]:
        """Generate detailed coverage report for diagnostics.
        
        Args:
            aggregated: AggregatedEntities result
            
        Returns:
            Dictionary with coverage diagnostics
        """
        if not aggregated.coverage_metrics:
            return {"error": "No coverage metrics available"}
        
        metrics = aggregated.coverage_metrics
        
        return {
            "summary": {
                "total_chunks": aggregated.total_chunks,
                "total_mentions": metrics.total_mentions,
                "unique_entities": metrics.unique_entities,
                "deduplication_ratio": f"{(1 - metrics.unique_entities / max(metrics.total_mentions, 1)) * 100:.1f}%"
            },
            "coverage": {
                "required_types": list(REQUIRED_ENTITY_TYPES),
                "coverage_status": metrics.coverage_status,
                "missing_required": metrics.missing_required_types,
                "all_types_covered": len(metrics.missing_required_types) == 0
            },
            "mentions_by_type": metrics.mentions_by_type,
            "dropped_mentions": {
                "count": len(metrics.dropped_mentions),
                "by_type": self._group_dropped_by_type(metrics.dropped_mentions)
            },
            "fallback": {
                "applied": metrics.fallback_applied,
                "entities_added": len(metrics.fallback_entities) if metrics.fallback_entities else 0
            }
        }
    
    def _group_dropped_by_type(self, dropped_mentions: List[Dict[str, Any]]) -> Dict[str, int]:
        """Group dropped mentions by entity type.
        
        Args:
            dropped_mentions: List of dropped mention dicts
            
        Returns:
            Dictionary mapping entity type to count
        """
        grouped = {}
        for mention in dropped_mentions:
            entity_type = mention.get("entity_type", "UNKNOWN")
            grouped[entity_type] = grouped.get(entity_type, 0) + 1
        return grouped
