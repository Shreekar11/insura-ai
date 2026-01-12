from temporalio import workflow
from datetime import timedelta
from typing import Optional, List
from temporalio.common import RetryPolicy
from app.utils.workflow_schemas import validate_workflow_output, IndexingOutputSchema

@workflow.defn
class IndexingWorkflow:
    """Child worklfow for generating vector embeddings and storing the embeddings in pgvector as vector database"""

    @workflow.run
    async def run(
        self, 
        workflow_id: str, 
        document_id: str,
        target_sections: Optional[list[str]] = None
    ) -> dict:

        workflow.logger.info(f"Starting vector indexing for document: {document_id}")

        vector_indexing_result = await workflow.execute_activity(
            "generate_embeddings_activity",
            args=[document_id, workflow_id, target_sections],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3
            )
        )

        graph_construction_result = await workflow.execute_activity(
            "construct_knowledge_graph_activity",
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
            "vector_indexed": True,
            "graph_constructed": True,
            "chunks_indexed": vector_indexing_result.get("chunks_embedded", 0),
            "entities_created": graph_construction_result.get("entities_created", 0),
            "relationships_created": graph_construction_result.get("relationships_created", 0),
            "embeddings_linked": graph_construction_result.get("embeddings_linked", 0),
        }

        validated_output = validate_workflow_output(
            output,
            IndexingOutputSchema,
            "IndexingWorkflow"
        )

        return validated_output