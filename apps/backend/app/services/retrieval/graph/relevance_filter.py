"""
Graph Relevance Filter Service

This service scores graph traversal results and hydrates sparse nodes
with full text content from PostgreSQL when necessary.
"""

from uuid import UUID
from typing import List, Dict, Any, Optional

from app.repositories.entity_repository import EntityRepository
from app.schemas.query import GraphTraversalResult, ExtractedQueryEntities
from app.services.retrieval.constants import (
    INTENT_SECTION_BOOSTS,
    ENTITY_MATCH_BOOST,
    RECENCY_BOOST_MAX
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GraphRelevanceFilterService:
    """Filter and score results from graph traversal."""

    def __init__(self, entity_repo: EntityRepository):
        """Initialize with PG entity repository."""
        self.entity_repo = entity_repo

    async def filter_and_score(
        self,
        traversal_results: List[GraphTraversalResult],
        extracted_entities: ExtractedQueryEntities,
        intent: str,
        workflow_id: UUID
    ) -> List[GraphTraversalResult]:
        """
        Score Results and hydrate sparse nodes.
        
        Args:
            traversal_results: Results from GraphTraverserService
            extracted_entities: Entities extracted from query
            intent: User intent
            workflow_id: Workflow scope/id
            
        Returns:
            Scored and hydrated results
        """
        if not traversal_results:
            return []

        scored_results = []
        
        # Get section boosts for this intent
        section_boosts = INTENT_SECTION_BOOSTS.get(intent, {})

        for result in traversal_results:
            # 1. Base score starts high (1.0) and decays with distance
            # Distance penalty: score = 0.9^distance
            score = 0.9 ** result.distance
            
            # 2. Section boost
            if result.source_section:
                section_type = result.source_section.lower()
                boost = section_boosts.get(section_type, 0.0)
                score += boost
                
            # 3. Entity match boost
            # If the node's entity type matches one of the types in the query
            entity_type = result.entity_type.lower()
            if entity_type in [t.lower() for t in extracted_entities.coverage_types]:
                score += ENTITY_MATCH_BOOST
                
            # Check for name/title overlaps if properties exist
            node_name = (
                result.properties.get("name") or 
                result.properties.get("title") or 
                result.properties.get("term")
            )
            if node_name:
                for entity_name in extracted_entities.entity_names:
                    if entity_name.lower() in node_name.lower():
                        score += ENTITY_MATCH_BOOST
                        break
            
            # Apply final score
            result.relevance_score = score
            
            # 4. Hydration Check: Sparse nodes (like Exclusions) often lack text in Neo4j
            # especially if the indexing logic only put name/type there.
            # If the node has very few properties or is a known sparse type, fetch from PG.
            if self._is_sparse(result):
                await self._hydrate_from_pg(result, workflow_id)
                
            scored_results.append(result)

        # Sort by relevance score descending
        scored_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return scored_results

    def _is_sparse(self, result: GraphTraversalResult) -> bool:
        """Check if a node is likely sparse and needs hydration."""
        # Known sparse types from analysis
        if result.entity_type in ["Exclusion", "Condition"]:
            # If description or text is missing, it's sparse
            if not result.properties.get("description") and not result.properties.get("definition_text"):
                return True
        
        # Generic check for property count if needed
        return len(result.properties) < 3

    async def _hydrate_from_pg(self, result: GraphTraversalResult, workflow_id: UUID) -> None:
        """Fetch full attributes from PostgreSQL to enrich the graph result."""
        try:
            # Use the canonical_key (which is stored as 'id' in Neo4j) to fetch from PG
            canonical_key = result.properties.get("id")
            if not canonical_key:
                return

            entity = await self.entity_repo.get_by_key(result.entity_type, canonical_key)
            if entity and entity.attributes:
                # Merge PG attributes into result properties
                # PG attributes are often richer (contains source_text, full description)
                result.properties.update(entity.attributes)
                
                # If source_text is available in PG attributes, ensure it's in properties
                if entity.attributes and "description" not in result.properties:
                    desc = entity.attributes.get("description") or entity.attributes.get("source_text")
                    if desc:
                        result.properties["description"] = desc

                LOGGER.debug(
                    f"Hydrated sparse node {result.entity_type}:{canonical_key} from PostgreSQL",
                    extra={"entity_id": str(entity.id)}
                )
        except Exception as e:
            LOGGER.warning(f"Failed to hydrate node from PG: {e}")
