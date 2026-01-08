from temporalio import workflow
from datetime import timedelta
from temporalio.common import RetryPolicy
from app.utils.workflow_schemas import validate_workflow_output, VectorIndexingOutputSchema

class VectorIndexingWorkflow:
    """Child worklfow for generating vector embeddings and storing the embeddings in pgvector as vector database"""
    @workflow.defn
    async def run(self, workflow_id: str, document_id: str) -> dict:

        workflow.logger.info(f"Starting vector indexing for document: {document_id}")

        embedding_result = await workflow.execute_activity(
            "generate_embeddings_activity",
            args=[document_id, workflow_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3
            )
        )

        output = {
            "workflow_id": workflow_id,
            "document_id": document_id,
            "indexed": True,
            "chunks_indexed": embedding_result.get("chunks_embedded", 0)
        }

        validated_output = validate_workflow_output(
            output,
            VectorIndexingOutputSchema,
            "VectorIndexingWorkflow"
        )

        return validated_output