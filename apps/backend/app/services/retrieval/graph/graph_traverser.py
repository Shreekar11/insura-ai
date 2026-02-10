"""
Graph Traverser Service

This service executes adaptive Neo4j traversals based on starting nodes
and intent-driven configuration.
"""

from uuid import UUID
from typing import List, Dict, Any, Optional

from app.core.neo4j_client import Neo4jClientManager
from app.schemas.query import GraphNode, GraphTraversalResult
from app.services.retrieval.constants import (
    TRAVERSAL_CONFIG,
    TRAVERSAL_QUERY_TEMPLATE
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GraphTraverserService:
    """Performs adaptive graph traversal starting from mapped nodes."""

    def __init__(self, neo4j_client: Neo4jClientManager):
        """Initialize with Neo4j client."""
        self.neo4j_client = neo4j_client

    async def traverse(
        self,
        start_nodes: List[GraphNode],
        intent: str,
        workflow_id: UUID
    ) -> List[GraphTraversalResult]:
        """
        Execute adaptive traversal from starting nodes.
        
        Args:
            start_nodes: Nodes mapped from vector search
            intent: User intent (QA, ANALYSIS, AUDIT)
            workflow_id: Workflow scope
            
        Returns:
            List of traversal results with relationship context
        """
        if not start_nodes:
            return []

        # Get traversal config for this intent
        config = TRAVERSAL_CONFIG.get(intent, TRAVERSAL_CONFIG["QA"])
        max_depth = config["max_depth"]
        edge_types = config["edge_types"]
        max_nodes = config["max_nodes"]

        # Build edge filter for Cypher: *1..2 or *1..2:TYPE1|TYPE2
        depth_range = f"1..{max_depth}"
        
        if edge_types:
            # Join and upper-case edge types
            edge_filter = "|".join(edge_types)
            path_spec = f":{edge_filter}*{depth_range}"
        else:
            # All edge types
            path_spec = f"*{depth_range}"

        # Collect entity_ids from start nodes
        # Using the internal ID/entity_id that was used during mapping
        start_entity_ids = [n.entity_id for n in start_nodes]
        
        try:
            # Construct final query by inserting the dynamic path spec
            query = TRAVERSAL_QUERY_TEMPLATE.format(edge_filter=path_spec)
            
            parameters = {
                "start_entity_ids": start_entity_ids,
                "workflow_id": str(workflow_id),
                "max_nodes": max_nodes
            }
            
            records = await self.neo4j_client.run_query(query, parameters)
            
            traversal_results = []
            for record in records:
                try:
                    result = GraphTraversalResult.from_neo4j(record)
                    traversal_results.append(result)
                except Exception as e:
                    LOGGER.error(f"Failed to parse GraphTraversalResult from record: {e}")
                    
            LOGGER.info(
                f"Completed graph traversal. Starts: {start_entity_ids}, Results: {len(traversal_results)}",
                extra={
                    "intent": intent,
                    "start_entity_ids": start_entity_ids,
                    "traversal_results_count": len(traversal_results),
                    "max_depth": max_depth,
                    "workflow_id": str(workflow_id)
                }
            )
            
            # Log individual traversal paths
            if traversal_results:
                paths_log = []
                for res in traversal_results[:5]:  # Log first 5 paths
                    path_str = f"{res.node_id} -{res.relationship_chain}-> {res.entity_type}:{res.properties.get('name', 'unnamed')}"
                    paths_log.append(path_str)
                
                LOGGER.info(
                    f"Sample traversal paths: {paths_log}",
                    extra={"count": len(traversal_results)}
                )

            return traversal_results

        except Exception as e:
            LOGGER.error(
                f"Error during graph traversal: {e}",
                extra={
                    "intent": intent,
                    "workflow_id": str(workflow_id)
                }
            )
            return []
