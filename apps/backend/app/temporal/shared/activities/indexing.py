from temporalio import activity
from uuid import UUID
from typing import List, Dict, Tuple, Optional, Any
from app.core.database import async_session_maker
from app.services.summarized.services.indexing.vector.generate_embeddings import GenerateEmbeddingsService
from app.services.summarized.services.indexing.vector.chunk_embedding_service import ChunkEmbeddingService
from app.services.summarized.services.indexing.graph.graph_service import GraphService
from app.utils.logging import get_logger
from app.core.neo4j_client import Neo4jClientManager
from app.temporal.core.activity_registry import ActivityRegistry

logger = get_logger(__name__)


@ActivityRegistry.register("shared", "generate_embeddings_activity")
@activity.defn
async def generate_embeddings_activity(
    document_id: str, 
    workflow_id: str,
    target_sections: Optional[list[str]] = None
) -> dict:
    """Temporal activity to generate vector embeddings for an insurance document."""
    try:
        async with async_session_maker() as session:
            service = GenerateEmbeddingsService(session)
            result = await service.execute(UUID(document_id), UUID(workflow_id), target_sections)
            return {
                "chunks_embedded": result.chunks_embedded,
                "vector_dimension": result.vector_dimension,
                "status": "completed",
                "storage_details": result.storage_details
            }
    except Exception as e:
        logger.error(f"Embedding generation activity failed for {document_id}: {e}", exc_info=True)
        raise


@ActivityRegistry.register("shared", "generate_chunk_embeddings_activity")
@activity.defn
async def generate_chunk_embeddings_activity(
    document_id: str,
    workflow_id: str,
) -> dict:
    """Temporal activity to generate chunk-level embeddings for citation resolution."""
    try:
        async with async_session_maker() as session:
            service = ChunkEmbeddingService(session)
            result = await service.generate_chunk_embeddings(
                UUID(document_id), UUID(workflow_id)
            )
            return {
                "chunks_embedded": result["chunks_embedded"],
                "total_chunks": result.get("total_chunks", 0),
                "status": result.get("status", "completed"),
            }
    except Exception as e:
        logger.error(
            f"Chunk embedding generation activity failed for {document_id}: {e}",
            exc_info=True,
        )
        raise


@ActivityRegistry.register("shared", "create_citations_activity")
@activity.defn
async def create_citations_activity(
    document_id: str,
    effective_coverages: list[dict],
    effective_exclusions: list[dict],
) -> dict:
    """Temporal activity to create citations after chunk embeddings are available.

    Runs after chunk embedding generation so that Tier 2 semantic search
    can find matching chunks in the vector_embeddings table.
    """
    try:
        async with async_session_maker() as session:
            from app.services.citation.citation_creation_service import CitationCreationService

            service = CitationCreationService(session)
            result = await service.create_citations_from_synthesis(
                document_id=UUID(document_id),
                effective_coverages=effective_coverages,
                effective_exclusions=effective_exclusions,
            )
            return {
                "created_count": result.get("created_count", 0),
                "skipped_count": result.get("skipped_count", 0),
                "error_count": len(result.get("errors", [])),
                "resolution_stats": result.get("resolution_stats", {}),
                "status": "completed",
            }
    except Exception as e:
        logger.error(
            f"Citation creation activity failed for {document_id}: {e}",
            exc_info=True,
        )
        raise


@ActivityRegistry.register("shared", "construct_knowledge_graph_activity")
@activity.defn
async def construct_knowledge_graph_activity(document_id: str, workflow_id: str) -> dict:
    """Temporal activity to construct knowledge graph for an insurance document."""
    try:
        neo4j_driver = await Neo4jClientManager.get_driver()
        async with async_session_maker() as db_session:
            graph_service = GraphService(neo4j_driver, db_session)
            result = await graph_service.execute(UUID(workflow_id), UUID(document_id))
            return {
                "status": "completed",
                "entities_created": result["entities_created"],
                "relationships_created": result["relationships_created"],
                "embeddings_linked": result["embeddings_linked"]
            }
    except Exception as e:
        logger.error(f"Knowledge graph construction activity failed for {document_id}: {e}", exc_info=True)
        raise
