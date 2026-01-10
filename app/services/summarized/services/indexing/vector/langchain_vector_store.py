from typing import Any, Iterable, List, Optional, Tuple, Type
from uuid import UUID

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from app.repositories.vector_embedding_repository import VectorEmbeddingRepository


class BridgedVectorStore(VectorStore):
    """Custom LangChain VectorStore that bridges to our existing VectorEmbeddingRepository.
    
    This allows us to leverage LangChain retrievers (MultiQuery, MMR, etc.)
    without changing our database schema or losing our custom metadata fields.
    """

    def __init__(
        self,
        repository: VectorEmbeddingRepository,
        embeddings: Embeddings,
    ):
        import asyncio
        self._repository = repository
        self._embeddings = embeddings
        self._lock = asyncio.Lock()

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Not implemented as we handle indexing via GenerateEmbeddingsService."""
        raise NotImplementedError("Use GenerateEmbeddingsService for adding texts")

    async def similarity_search(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> List[Document]:
        """Perform a similarity search using the repository."""
        query_embedding = self._embeddings.embed_query(query)
        
        # Extract filters from kwargs
        document_id = kwargs.get("document_id")
        section_type = kwargs.get("section_type")
        filters = kwargs.get("filters")
        max_distance = kwargs.get("max_distance")

        # Convert document_id to UUID if string
        if isinstance(document_id, str):
            document_id = UUID(document_id)

        # Use the existing semantic_search method
        # We need to run this in an async context, but LangChain's VectorStore is sync-based
        # (though there are async versions). We'll implement the async search below.
        raise NotImplementedError("Use asimilarity_search instead")

    async def asimilarity_search(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> List[Document]:
        """Asynchronous similarity search."""
        query_embedding = self._embeddings.embed_query(query)
        
        document_id = kwargs.get("document_id")
        section_type = kwargs.get("section_type")
        filters = kwargs.get("filters")
        max_distance = kwargs.get("max_distance")

        if isinstance(document_id, str):
            document_id = UUID(document_id)

        async with self._lock:
            results = await self._repository.semantic_search(
                embedding=query_embedding,
                top_k=k,
                document_id=document_id,
                section_type=section_type,
                filters=filters,
                max_distance=max_distance
            )

        return [
            Document(
                page_content=str(res.entity_id),  # We don't store text, so we return ID
                metadata={
                    "document_id": str(res.document_id),
                    "workflow_id": str(res.workflow_id),
                    "section_type": res.section_type,
                    "entity_type": res.entity_type,
                    "entity_id": res.entity_id,
                    "effective_date": str(res.effective_date) if res.effective_date else None,
                    "location_id": res.location_id,
                }
            )
            for res in results
        ]

    async def asimilarity_search_with_score(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> List[Tuple[Document, float]]:
        """Asynchronous similarity search with distance scores."""
        query_embedding = self._embeddings.embed_query(query)
        
        document_id = kwargs.get("document_id")
        section_type = kwargs.get("section_type")
        
        async with self._lock:
            results_with_dist = await self._repository.get_embeddings_with_distance(
                embedding=query_embedding,
                document_id=document_id,
                section_type=section_type,
                max_distance=kwargs.get("max_distance", 0.7)
            )

        return [
            (
                Document(
                    page_content=str(res.entity_id),
                    metadata={
                        "document_id": str(res.document_id),
                        "workflow_id": str(res.workflow_id),
                        "section_type": res.section_type,
                        "entity_type": res.entity_type,
                        "entity_id": res.entity_id,
                        "effective_date": str(res.effective_date) if res.effective_date else None,
                        "location_id": res.location_id,
                    }
                ),
                float(dist)
            )
            for res, dist in results_with_dist[:k]
        ]

    @classmethod
    def from_texts(
        cls: Type["BridgedVectorStore"],
        texts: List[str],
        embedding: Embeddings,
        metadatas: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> "BridgedVectorStore":
        """Not implemented."""
        raise NotImplementedError("Use GenerateEmbeddingsService")
