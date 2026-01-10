from temporalio import activity
from uuid import UUID
from app.core.database import async_session_maker
from app.services.summarized.services.indexing.vector.generate_embeddings import GenerateEmbeddingsService
from app.services.summarized.services.indexing.graph.graph_builder import GraphBuilder
from app.utils.logging import get_logger
from app.core.neo4j_client import Neo4jClientManager

logger = get_logger(__name__)


@activity.defn
async def generate_embeddings_activity(document_id: str, workflow_id: str) -> dict:
    """Temporal activity to generate vector embeddings for an insurance document.
    
    This activity:
    1. Loads the extracted sections for the document.
    2. Generates semantic text templates.
    3. Computes vector embeddings using locally-hosted models.
    4. Persists the embeddings for later semantic recall.
    
    Args:
        document_id: UUID of the document as a string
        
    Returns:
        Dictionary with processing results: chunks_embedded, dimension, status
    """
    try:
        logger.info(f"Starting embedding generation activity for document {document_id}")
        
        async with async_session_maker() as session:
            service = GenerateEmbeddingsService(session)
            # result is an EmbeddingResult dataclass
            result = await service.execute(UUID(document_id), UUID(workflow_id))
            
            logger.info(
                f"Embedding generation completed for {document_id}: "
                f"{result.chunks_embedded} units embedded"
            )
            
            return {
                "chunks_embedded": result.chunks_embedded,
                "vector_dimension": result.vector_dimension,
                "status": "completed",
                "storage_details": result.storage_details
            }
            
    except Exception as e:
        logger.error(f"Embedding generation activity failed for {document_id}: {e}", exc_info=True)
        # Re-raise to let Temporal handle retry logic
        raise

@activity.defn
async def construct_knowledge_graph_activity(document_id: str, workflow_id: str) -> dict:
    """Temporal activity to construct knowledge graph for an insurance document."""
    try:
        logger.info(f"Starting knowledge graph construction activity for document {document_id}")
        neo4j_driver = await Neo4jClientManager.get_driver()
        async with async_session_maker() as db_session:
            graph_builder = GraphBuilder(neo4j_driver, db_session)

            result = await graph_builder.execute(UUID(workflow_id), UUID(document_id))

            logger.info(
                f"Knowledge graph construction completed for {document_id}: "
                f"{result.entities_created} entities created, "
                f"{result.relationships_created} relationships created, "
                f"{result.embeddings_linked} embeddings linked"
            )
            
            return {
                "status": "completed",
                "entities_created": result.entities_created,
                "relationships_created": result.relationships_created,
                "embeddings_linked": result.embeddings_linked
            }
            
    except Exception as e:
        logger.error(f"Knowledge graph construction activity failed for {document_id}: {e}", exc_info=True)
        # Re-raise to let Temporal handle retry logic
        raise