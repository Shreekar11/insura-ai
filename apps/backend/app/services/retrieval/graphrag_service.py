import time
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.query import (
    GraphRAGRequest,
    GraphRAGResponse,
    ResponseMetadata,
    SourceCitation,
    ContextPayload,
)
from app.core.neo4j_client import Neo4jClientManager
from app.repositories.entity_repository import EntityRepository
from app.services.retrieval.graph.graph_expansion import GraphExpansionService
from app.services.retrieval.graph.graph_traverser import GraphTraverserService
from app.services.retrieval.graph.node_mapper import NodeMapperService
from app.services.retrieval.graph.relevance_filter import GraphRelevanceFilterService
from app.services.retrieval.query_understanding.service import QueryUnderstandingService
from app.services.retrieval.vector.vector_retrieval_service import VectorRetrievalService
from app.services.retrieval.context.result_merger import ResultMergerService
from app.services.retrieval.context.hierarchical_builder import HierarchicalContextBuilder
from app.services.retrieval.context.context_formatter import format_context_for_llm
from app.services.retrieval.response.generation_service import ResponseGenerationService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GraphRAGService:
    """
    Top-level orchestrator for the GraphRAG retrieval pipeline (Stage 6).
    
    Coordinates:
    1. Query Understanding (Stage 1)
    2. Vector-Based Retrieval (Stage 2)
    3. Graph-Based Context Expansion (Stage 3)
    4. Context Assembly (Stage 4)
    5. LLM Response Generation (Stage 5)
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.query_understanding = QueryUnderstandingService(db_session)
        self.vector_retrieval = VectorRetrievalService(db_session)
        
        # Initialize Graph Expansion Sub-services
        self.node_mapper = NodeMapperService(Neo4jClientManager)
        self.graph_traverser = GraphTraverserService(Neo4jClientManager)
        self.entity_repo = EntityRepository(db_session)
        self.relevance_filter = GraphRelevanceFilterService(self.entity_repo)
        
        self.graph_expansion = GraphExpansionService(
            node_mapper=self.node_mapper,
            traverser=self.graph_traverser,
            relevance_filter=self.relevance_filter
        )
        
        self.result_merger = ResultMergerService()
        self.context_builder = HierarchicalContextBuilder()
        self.response_generator = ResponseGenerationService()

    async def query(
        self, workflow_id: UUID, request: GraphRAGRequest
    ) -> GraphRAGResponse:
        """
        Execute the full GraphRAG retrieval pipeline.
        
        Args:
            workflow_id: ID of the insurance workflow to query.
            request: The user's query and retrieval parameters.
            
        Returns:
            GraphRAGResponse with generated answer, citations, and metadata.
        """
        start_time = time.time()
        stage_latencies = {}
        
        # 1. Stage 1: Query Understanding
        s1_start = time.time()
        query_plan = await self.query_understanding.understand_query(
            query=request.query,
            workflow_id=workflow_id,
            target_document_ids=request.document_ids,
        )
        # Apply intent override if provided
        if request.intent_override:
            query_plan.intent = request.intent_override
            # Map intent to traversal depth if overridden
            depth_map = {"QA": 1, "ANALYSIS": 2, "AUDIT": 3}
            query_plan.traversal_depth = depth_map.get(request.intent_override, 1)
            
        stage_latencies["query_understanding"] = int((time.time() - s1_start) * 1000)

        # Early exit for GENERAL intent (conversational queries)
        if query_plan.intent == "GENERAL":
            from app.services.retrieval.constants import GENERAL_QUERY_RESPONSE
            
            LOGGER.info(
                "Short-circuiting GraphRAG pipeline for GENERAL intent",
                extra={"query": request.query[:100]}
            )
            
            total_latency_ms = int((time.time() - start_time) * 1000)
            metadata = ResponseMetadata(
                intent="GENERAL",
                traversal_depth=0,
                vector_results_count=0,
                graph_results_count=0,
                merged_results_count=0,
                full_text_count=0,
                summary_count=0,
                total_context_tokens=0,
                latency_ms=total_latency_ms,
                stage_latencies=stage_latencies,
                graph_available=True,
                fallback_mode=False
            )
            
            return GraphRAGResponse(
                answer=GENERAL_QUERY_RESPONSE.strip(),
                sources=[],
                metadata=metadata,
                timestamp=datetime.now(timezone.utc)
            )

        # 2. Stage 2: Vector Retrieval
        s2_start = time.time()
        vector_results = await self.vector_retrieval.retrieve(query_plan)
        vector_dicts = [res.model_dump() for res in vector_results]
        stage_latencies["vector_retrieval"] = int((time.time() - s2_start) * 1000)

        # 3. Stage 3: Graph Expansion
        s3_start = time.time()
        graph_results = []
        graph_available = True
        fallback_mode = False
        
        try:
            graph_results = await self.graph_expansion.expand(
                vector_results=vector_results,
                query_plan=query_plan,
                workflow_id=workflow_id
            )
        except Exception as e:
            LOGGER.error(f"Graph expansion failed, falling back to vector-only: {e}", exc_info=True)
            graph_available = False
            fallback_mode = True
            
        stage_latencies["graph_expansion"] = int((time.time() - s3_start) * 1000)

        # 4. Stage 4: Context Assembly
        s4_start = time.time()
        merged_results = self.result_merger.merge(
            vector_results=vector_dicts,
            graph_results=graph_results
        )
        
        context_payload: ContextPayload = self.context_builder.build_context(
            results=merged_results,
            max_tokens=request.max_context_tokens
        )
        
        markdown_context = format_context_for_llm(context_payload)
        stage_latencies["context_assembly"] = int((time.time() - s4_start) * 1000)

        # 5. Stage 5: Response Generation
        s5_start = time.time()
        generated_response = await self.response_generator.generate_response(
            query=request.query,
            context=context_payload
        )
        
        stage_latencies["response_generation"] = int((time.time() - s5_start) * 1000)

        # Final Metadata and Response Assembly
        total_latency_ms = int((time.time() - start_time) * 1000)
        
        if vector_results:
            # detailed logging for top 3 vector results
            detailed_vector_log = []
            for res in vector_results[:3]:
                content_snippet = res.content[:100] if res.content else "EMPTY"
                detailed_vector_log.append(
                    f"[doc:{res.document_name} | sec:{res.section_type}] score:{res.final_score:.2f} content:{content_snippet}..."
                )
            
            LOGGER.info(
                f"Top 3 Vector Results (intent: {query_plan.intent} | count: {len(vector_results)} | "
                f"top_score: {vector_results[0].final_score:.3f}):\n" + "\n".join(detailed_vector_log)
            )

        if graph_results:
            # detailed logging for top 3 graph results
            detailed_graph_log = []
            for res in graph_results[:3]:
                desc_snippet = res.properties.get('description', '')[:100]
                detailed_graph_log.append(
                    f"[{res.entity_type}:{res.properties.get('name', 'unnamed')}] chain:{res.relationship_chain} desc:{desc_snippet}..."
                )
            
            LOGGER.info(
                f"Top 3 Graph Results (count: {len(graph_results)}):\n" + "\n".join(detailed_graph_log)
            )
        LOGGER.info(
            f"Context assembly complete | total_results: {len(context_payload.full_text_results) + len(context_payload.summary_results)} | "
            f"full_text: {len(context_payload.full_text_results)} | "
            f"summaries: {len(context_payload.summary_results)} | "
            f"context_chars: {len(markdown_context)}"
        )
        metadata = ResponseMetadata(
            intent=query_plan.intent,
            traversal_depth=query_plan.traversal_depth,
            vector_results_count=len(vector_results),
            graph_results_count=len(graph_results),
            merged_results_count=len(merged_results),
            full_text_count=len(context_payload.full_text_results),
            summary_count=len(context_payload.summary_results),
            total_context_tokens=context_payload.token_count,
            latency_ms=total_latency_ms,
            stage_latencies=stage_latencies,
            graph_available=graph_available,
            fallback_mode=fallback_mode
        )

        return GraphRAGResponse(
            answer=generated_response.answer,
            sources=[],
            metadata=metadata,
            timestamp=datetime.now(timezone.utc)
        )
