"""Entity reconciliation service.

This service reconciles entities from LLM extraction with entities from
deterministic parsing, ensuring that canonical entity resolution never
starts from an empty set.
"""

from typing import List, Dict, Any
from uuid import UUID

from app.services.extraction.deterministic_parser import InsuranceEntityParser
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EntityReconciliationService:
    """Reconciles LLM entities with deterministic parser entities.
    
    This service merges entities from two sources:
    1. LLM extraction (higher confidence, semantic understanding)
    2. Deterministic parser (regex-based backstop)
    
    Strategy:
    - Prefer LLM entities when both sources find the same entity
    - Use parsed entities as backstop when LLM misses entities
    - Merge by entity type and normalized value
    
    Attributes:
        parser: InsuranceEntityParser instance
    """
    
    def __init__(self, parser: InsuranceEntityParser = None):
        """Initialize reconciliation service.
        
        Args:
            parser: Optional parser instance (creates default if None)
        """
        self.parser = parser or InsuranceEntityParser()
        
        LOGGER.info("Initialized EntityReconciliationService")
    
    def reconcile_entities(
        self,
        llm_entities: List[Dict[str, Any]],
        text: str,
        chunk_id: UUID = None
    ) -> List[Dict[str, Any]]:
        """Reconcile LLM entities with parsed entities.
        
        Args:
            llm_entities: Entities extracted by LLM
            text: Original text to parse
            chunk_id: Optional chunk ID for tracking
            
        Returns:
            Merged list of entities
        """
        LOGGER.debug(
            "Starting entity reconciliation",
            extra={
                "llm_entity_count": len(llm_entities),
                "chunk_id": str(chunk_id) if chunk_id else None
            }
        )
        
        # Parse entities using deterministic parser
        parsed_entities = self.parser.parse_all(text)
        
        # Merge entities
        merged_entities = self._merge_entities(
            llm_entities=llm_entities,
            parsed_entities=parsed_entities
        )
        
        # Track backstop statistics
        backstop_count = len(merged_entities) - len(llm_entities)
        
        if backstop_count > 0:
            LOGGER.info(
                f"Deterministic parser backstopped {backstop_count} entities",
                extra={
                    "llm_count": len(llm_entities),
                    "parsed_count": len(parsed_entities),
                    "merged_count": len(merged_entities),
                    "backstop_count": backstop_count,
                    "chunk_id": str(chunk_id) if chunk_id else None
                }
            )
        
        return merged_entities
    
    def _merge_entities(
        self,
        llm_entities: List[Dict[str, Any]],
        parsed_entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge LLM and parsed entities.
        
        Strategy:
        1. Start with all LLM entities (higher quality)
        2. For each parsed entity, check if LLM already found it
        3. If not found by LLM, add parsed entity as backstop
        
        Args:
            llm_entities: Entities from LLM
            parsed_entities: Entities from parser
            
        Returns:
            Merged entity list
        """
        merged = llm_entities.copy()
        
        # Build lookup of LLM entities by (type, normalized_value)
        llm_lookup = {}
        for entity in llm_entities:
            key = (
                entity.get("entity_type"),
                self._normalize_for_comparison(entity.get("normalized_value", ""))
            )
            llm_lookup[key] = entity
        
        # Add parsed entities that weren't found by LLM
        backstop_added = 0
        
        for parsed_entity in parsed_entities:
            key = (
                parsed_entity.get("entity_type"),
                self._normalize_for_comparison(parsed_entity.get("normalized_value", ""))
            )
            
            if key not in llm_lookup:
                # LLM didn't find this entity, add parsed version as backstop
                merged.append(parsed_entity)
                backstop_added += 1
                
                LOGGER.debug(
                    f"Backstop: Added {parsed_entity.get('entity_type')} from parser",
                    extra={
                        "entity_type": parsed_entity.get("entity_type"),
                        "normalized_value": parsed_entity.get("normalized_value"),
                        "confidence": parsed_entity.get("confidence")
                    }
                )
            else:
                # LLM found it, prefer LLM version (already in merged)
                llm_entity = llm_lookup[key]
                
                LOGGER.debug(
                    f"Duplicate: LLM already found {parsed_entity.get('entity_type')}",
                    extra={
                        "entity_type": parsed_entity.get("entity_type"),
                        "llm_confidence": llm_entity.get("confidence"),
                        "parsed_confidence": parsed_entity.get("confidence")
                    }
                )
        
        if backstop_added > 0:
            LOGGER.info(
                f"Added {backstop_added} backstop entities from parser",
                extra={"backstop_count": backstop_added}
            )
        
        return merged
    
    def _normalize_for_comparison(self, value: str) -> str:
        """Normalize value for comparison.
        
        Args:
            value: Value to normalize
            
        Returns:
            Normalized value for comparison
        """
        if not value:
            return ""
        
        # Lowercase, remove whitespace and special chars for comparison
        normalized = value.lower().strip()
        normalized = normalized.replace(" ", "").replace("-", "").replace("_", "")
        
        return normalized
    
    def get_backstop_coverage(
        self,
        llm_entities: List[Dict[str, Any]],
        merged_entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Get backstop coverage statistics.
        
        Args:
            llm_entities: Original LLM entities
            merged_entities: Merged entities after reconciliation
            
        Returns:
            Dictionary with backstop statistics
        """
        backstop_entities = [
            e for e in merged_entities
            if e.get("source") == "deterministic_parser"
        ]
        
        # Count by type
        backstop_by_type = {}
        for entity in backstop_entities:
            entity_type = entity.get("entity_type", "UNKNOWN")
            backstop_by_type[entity_type] = backstop_by_type.get(entity_type, 0) + 1
        
        return {
            "llm_count": len(llm_entities),
            "merged_count": len(merged_entities),
            "backstop_count": len(backstop_entities),
            "backstop_percentage": (len(backstop_entities) / max(len(merged_entities), 1)) * 100,
            "backstop_by_type": backstop_by_type
        }
