"""
Node Mapper Service

This service maps VectorSearchResult objects to Neo4j entity nodes
to provide starting points for graph traversal.
"""

from uuid import UUID
from typing import List, Dict, Any

from app.core.neo4j_client import Neo4jClientManager
from app.schemas.query import VectorSearchResult, GraphNode
from app.services.retrieval.constants import NODE_MAPPING_QUERY
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
        Map vector results to Neo4j nodes.
        
        Uses the `entity_id` from vector results to find corresponding 
        nodes in Neo4j that have this ID in their `vector_entity_ids` property
        or as their primary `id`.
        
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

        # Clean duplicates
        unique_entity_ids = list(set(entity_ids))
        
        try:
            # Execute batch query            
            parameters = {
                "entity_ids": unique_entity_ids,
                "workflow_id": str(workflow_id)
            }
            
            records = await self.neo4j_client.run_query(NODE_MAPPING_QUERY, parameters)
            
            mapped_nodes = []
            for record in records:
                try:
                    node = GraphNode.from_neo4j(record)
                    mapped_nodes.append(node)
                except Exception as e:
                    LOGGER.error(f"Failed to parse GraphNode from record: {e}")
                    
            LOGGER.info(
                f"Mapped {len(vector_results)} vector results to {len(mapped_nodes)} graph nodes. Inputs: {unique_entity_ids}",
                extra={
                    "vector_results_count": len(vector_results),
                    "input_entity_ids": unique_entity_ids,
                    "mapped_nodes_count": len(mapped_nodes),
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

    async def map_by_canonical_ids(
        self, 
        canonical_ids: List[UUID], 
        workflow_id: UUID
    ) -> List[GraphNode]:
        """
        Map canonical entity UUIDs to Neo4j nodes.
        
        Args:
            canonical_ids: List of canonical entity UUIDs
            workflow_id: Workflow scope
            
        Returns:
            List of GraphNode objects
        """
        if not canonical_ids:
            return []

        # The Neo4j node `id` is the `canonical_key` (string hash), 
        # not the UUID. However, Stage 0 bridge also added canonical_entity_id 
        # to some nodes or we can match by canonical_key if we had them.
        
        # Actually, GraphService stores `canonical_key` as `id`.
        # To map by UUID, we might need a separate query or have 
        # stored the UUID on the node.
        
        # Let's assume we primarily map via entity_id from vector results.
        return []
