"""
Node Mapper Service

This service maps VectorSearchResult objects to Neo4j entity nodes
to provide starting points for graph traversal.

Uses a two-tier matching strategy:
1. Primary: Match by vector_entity_ids property on entity nodes
2. Fallback: For unmapped entity_ids, fetch ALL entity nodes of the same
   type in the workflow (ensures coverage when canonical_entity_id bridge
   is incomplete)
"""

from uuid import UUID
from typing import List, Dict, Any

from app.core.neo4j_client import Neo4jClientManager
from app.schemas.query import VectorSearchResult, GraphNode
from app.services.retrieval.constants import (
    NODE_MAPPING_QUERY,
    NODE_MAPPING_FALLBACK_QUERY,
    SECTION_TO_ENTITY_LABEL,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NodeMapperService:
    """Maps vector search results to knowledge graph nodes."""

    def __init__(self, neo4j_client: Neo4jClientManager):
        """Initialize with Neo4j client."""
        self.neo4j_client = neo4j_client

    async def map_nodes(
        self,
        vector_results: List[VectorSearchResult],
        workflow_id: UUID
    ) -> List[GraphNode]:
        """
        Map vector results to Neo4j nodes using two-tier matching.

        Tier 1: Match via vector_entity_ids property (fast, exact).
        Tier 2: For unmapped entity_ids, fetch all entity nodes of the
                 same type in the workflow (ensures no Coverage/Exclusion
                 nodes are missed when canonical_entity_id bridge is incomplete).

        Args:
            vector_results: Results from VectorRetrievalService
            workflow_id: Workflow scope

        Returns:
            List of GraphNode objects mapped from the graph
        """
        if not vector_results:
            return []

        # Extract all entity_ids for batch lookup
        entity_ids = [r.entity_id for r in vector_results if r.entity_id]
        if not entity_ids:
            LOGGER.warning("No entity_ids found in vector results for node mapping")
            return []

        unique_entity_ids = list(set(entity_ids))

        try:
            # Tier 1: Primary match by vector_entity_ids
            parameters = {
                "entity_ids": unique_entity_ids,
                "workflow_id": str(workflow_id)
            }

            records = await self.neo4j_client.run_query(NODE_MAPPING_QUERY, parameters)

            mapped_nodes = []
            mapped_vector_ids: set[str] = set()
            for record in records:
                try:
                    node = GraphNode.from_neo4j(record)
                    mapped_nodes.append(node)
                    # Track which vector_entity_ids were matched
                    vids = node.properties.get("vector_entity_ids", [])
                    mapped_vector_ids.update(vids)
                except Exception as e:
                    LOGGER.error(f"Failed to parse GraphNode from record: {e}")

            # Determine which entity_ids weren't matched
            unmapped_ids = [eid for eid in unique_entity_ids if eid not in mapped_vector_ids]

            # Tier 2: Fallback matching for unmapped entity_ids
            if unmapped_ids:
                fallback_nodes = await self._fallback_match(
                    unmapped_ids, vector_results, mapped_nodes, workflow_id
                )
                mapped_nodes.extend(fallback_nodes)

            LOGGER.info(
                f"Mapped {len(vector_results)} vector results to {len(mapped_nodes)} graph nodes. "
                f"Inputs: {unique_entity_ids}",
                extra={
                    "vector_results_count": len(vector_results),
                    "input_entity_ids": unique_entity_ids,
                    "mapped_nodes_count": len(mapped_nodes),
                    "unmapped_count": len(unmapped_ids),
                    "fallback_used": len(unmapped_ids) > 0,
                    "workflow_id": str(workflow_id)
                }
            )

            return mapped_nodes

        except Exception as e:
            LOGGER.error(
                f"Error during node mapping: {e}",
                extra={"workflow_id": str(workflow_id)}
            )
            return []

    async def _fallback_match(
        self,
        unmapped_ids: list[str],
        vector_results: List[VectorSearchResult],
        already_mapped: List[GraphNode],
        workflow_id: UUID,
    ) -> List[GraphNode]:
        """Fallback: fetch entity nodes by label for unmapped vector results.

        For each unmapped entity_id, determine the entity type from the
        vector result's section_type, then fetch ALL entity nodes of that
        type in the workflow that weren't already mapped.
        """
        # Determine which entity labels we need to fetch
        labels_needed: set[str] = set()
        for eid in unmapped_ids:
            # Find the corresponding vector result to get section_type
            for vr in vector_results:
                if vr.entity_id == eid:
                    label = SECTION_TO_ENTITY_LABEL.get(vr.section_type)
                    if label:
                        labels_needed.add(label)
                    break

        if not labels_needed:
            return []

        # Collect already-mapped node IDs to exclude
        already_mapped_ids = [n.properties.get("id", "") for n in already_mapped]

        fallback_nodes = []
        for label in labels_needed:
            try:
                # Use parameterized label query (label is from our constant map, safe)
                query = NODE_MAPPING_FALLBACK_QUERY.format(label=label)
                parameters = {
                    "workflow_id": str(workflow_id),
                    "already_mapped_ids": already_mapped_ids,
                }
                records = await self.neo4j_client.run_query(query, parameters)

                for record in records:
                    try:
                        node = GraphNode.from_neo4j(record)
                        fallback_nodes.append(node)
                    except Exception as e:
                        LOGGER.error(f"Failed to parse fallback GraphNode: {e}")

                LOGGER.info(
                    f"Fallback matched {len(records)} {label} nodes",
                    extra={"label": label, "workflow_id": str(workflow_id)}
                )
            except Exception as e:
                LOGGER.warning(f"Fallback query failed for label {label}: {e}")

        return fallback_nodes
