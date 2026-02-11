"""
Graph Expansion Service

The top-level orchestrator for the GraphRAG pipeline.
It coordinates node mapping, traversal, and relevance filtering.
"""

import time
from uuid import UUID
from typing import List, Dict, Any

from app.schemas.query import (
    VectorSearchResult, 
    GraphTraversalResult, 
    QueryPlan
)
from app.services.retrieval.graph.node_mapper import NodeMapperService
from app.services.retrieval.graph.graph_traverser import GraphTraverserService
from app.services.retrieval.graph.relevance_filter import GraphRelevanceFilterService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GraphExpansionService:
    """Orchestrates graph expansion for Vector results."""

    def __init__(
        self,
        node_mapper: NodeMapperService,
        traverser: GraphTraverserService,
        relevance_filter: GraphRelevanceFilterService
    ):
        """Initialize with sub-services."""
        self.node_mapper = node_mapper
        self.traverser = traverser
        self.relevance_filter = relevance_filter

    async def expand(
        self,
        vector_results: List[VectorSearchResult],
        query_plan: QueryPlan,
        workflow_id: UUID
    ) -> List[GraphTraversalResult]:
        """
        Orchestrate graph expansion from vector results.
        
        Orchestration flow:
        1. Map vector results to graph nodes
        2. Traverse graph from mapped nodes based on intent
        3. Score and hydrate traversal results
        
        Args:
            vector_results: Results from vector retrieval
            query_plan: Plan from query understanding (contains intent and entities)
            workflow_id: Workflow scope
            
        Returns:
            List of scored and hydrated GraphTraversalResult objects
        """
        start_time = time.time()
        
        if not vector_results:
            return []

        try:
            # 1. Node Mapping
            # Bridge the vector search results to graph starting points
            mapped_nodes = await self.node_mapper.map_nodes(
                vector_results, 
                workflow_id
            )
            
            if not mapped_nodes:
                LOGGER.info(
                    "No graph nodes found for vector results",
                    extra={"workflow_id": str(workflow_id)}
                )
                return []

            # Log sample of mapped nodes
            sample_mapped = [n.properties.get('name', 'unnamed') for n in mapped_nodes[:5]]
            LOGGER.info(
                f"Mapped {len(mapped_nodes)} nodes | sample: {sample_mapped}"
            )

            # 2. Graph Traversal
            # Navigate relationships based on intent (QA/ANALYSIS/AUDIT)
            traversal_results = await self.traverser.traverse(
                mapped_nodes,
                query_plan.intent,
                workflow_id
            )
            
            LOGGER.info(
                f"Graph traversal found {len(traversal_results)} paths"
            )
            
            if not traversal_results:
                return []

            # 3. Relevance Filtering & Hydration
            # Score results and fetch missing text from PostgreSQL
            final_results = await self.relevance_filter.filter_and_score(
                traversal_results,
                query_plan.extracted_entities,
                query_plan.intent,
                workflow_id
            )
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            LOGGER.info(
                f"Graph expansion complete | workflow: {workflow_id} | vector_hits: {len(vector_results)} | "
                f"mapped: {len(mapped_nodes)} | paths: {len(traversal_results)} | "
                f"expanded: {len(final_results)} | latency: {latency_ms}ms"
            )
            
            return final_results

        except Exception as e:
            LOGGER.error(
                f"Graph expansion pipeline failed: {e}",
                exc_info=True,
                extra={"workflow_id": str(workflow_id)}
            )
            # return empty instead of failing entire pipeline
            return []
