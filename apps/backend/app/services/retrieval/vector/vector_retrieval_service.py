"""
Vector-Based Retrieval Service (Stage 2)

Orchestrates the full vector retrieval pipeline:
1. Embed expanded queries using SentenceTransformer
2. Execute multi-query semantic search with filters
3. Resolve content from SectionExtraction data
4. Apply intent-aware reranking
5. Return scored VectorSearchResult list
"""

import asyncio
from pathlib import Path
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, VectorEmbedding
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.schemas.query import QueryPlan, VectorSearchResult
from app.services.retrieval.constants import (
    DEFAULT_DISTANCE_THRESHOLD,
    DEFAULT_VECTOR_TOP_K,
)
from app.services.retrieval.vector.reranker import IntentReranker
from app.services.summarized.services.indexing.vector.vector_template_service import (
    VectorTemplateService,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Module-level singleton for the embedding model (expensive to load)
_embedding_model: SentenceTransformer | None = None


def _get_embedding_model() -> SentenceTransformer:
    """Get or lazily load the shared SentenceTransformer model."""
    global _embedding_model
    if _embedding_model is None:
        LOGGER.info("Loading embedding model: all-MiniLM-L6-v2")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


class VectorRetrievalService:
    """Orchestrates vector-based retrieval (Stage 2 of the GraphRAG pipeline).

    Takes a QueryPlan from Stage 1, embeds expanded queries, searches the
    vector store, resolves content, applies intent-aware reranking, and
    returns a scored list of VectorSearchResult objects.
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.vector_repo = VectorEmbeddingRepository(db_session)
        self.section_repo = SectionExtractionRepository(db_session)
        self.template_service = VectorTemplateService()
        self.reranker = IntentReranker()

    async def retrieve(
        self,
        query_plan: QueryPlan,
        top_k: int = DEFAULT_VECTOR_TOP_K,
        max_distance: float = DEFAULT_DISTANCE_THRESHOLD,
    ) -> list[VectorSearchResult]:
        """Execute vector retrieval pipeline.

        Args:
            query_plan: QueryPlan from Stage 1 (query understanding)
            top_k: Maximum number of results to return
            max_distance: Maximum cosine distance threshold (0-2)

        Returns:
            List of VectorSearchResult, sorted by final_score descending
        """
        workflow_id = query_plan.workflow_context.workflow_id

        # Step 1: Embed expanded queries
        query_embeddings = await self._embed_queries(query_plan.expanded_queries)
        if not query_embeddings:
            LOGGER.warning("No query embeddings generated")
            return []

        # Step 2: Multi-query semantic search
        raw_results = await self.vector_repo.semantic_search_multi_query(
            embeddings=query_embeddings,
            top_k=top_k,
            workflow_id=workflow_id,
            document_ids=query_plan.target_document_ids,
            section_types=query_plan.section_type_filters or None,
            entity_types=query_plan.entity_type_filters or None,
            max_distance=max_distance,
        )

        if not raw_results:
            LOGGER.info(
                "No vector results found",
                extra={"workflow_id": str(workflow_id)},
            )
            return []

        LOGGER.info(
            "Raw vector results",
            extra={
                "count": len(raw_results),
                "best_distance": raw_results[0][1] if raw_results else None,
            },
        )

        # Step 3: Rerank with intent-aware boosting
        reranked = self.reranker.rerank(
            results=raw_results,
            intent=query_plan.intent,
            extracted_entities=query_plan.extracted_entities,
            entity_type_filters=query_plan.entity_type_filters or None,
        )

        # Step 4: Resolve content and document names in bulk
        results = await self._resolve_results(reranked, workflow_id)

        # Log sample content for debugging
        if results:
            sample = results[0].content[:100] if results[0].content else "EMPTY"
            LOGGER.info(f"Resolved content for first result: {sample}")

        LOGGER.info(
            "Vector retrieval complete",
            extra={
                "intent": query_plan.intent,
                "raw_count": len(raw_results),
                "final_count": len(results),
                "top_score": results[0].final_score if results else 0.0,
            },
        )

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _embed_queries(self, queries: list[str]) -> list[list[float]]:
        """Embed query strings using SentenceTransformer (offloaded to thread)."""
        if not queries:
            return []

        model = _get_embedding_model()
        # SentenceTransformer.encode is CPU-bound; run in a thread
        embeddings = await asyncio.to_thread(model.encode, queries)
        return [emb.tolist() for emb in embeddings]

    async def _resolve_results(
        self,
        reranked: list[tuple[VectorEmbedding, float, float]],
        workflow_id: UUID,
    ) -> list[VectorSearchResult]:
        """Convert reranked (VectorEmbedding, similarity, final_score) tuples
        into VectorSearchResult objects by resolving content and document names.
        """
        if not reranked:
            return []

        # Collect unique document_ids for bulk name resolution
        doc_ids = list({emb.document_id for emb, _, _ in reranked})
        doc_names = await self._resolve_document_names(doc_ids)

        # Collect unique (document_id, section_type) pairs for content resolution
        section_keys = list({(emb.document_id, emb.section_type) for emb, _, _ in reranked})
        content_map = await self._resolve_content_map(section_keys, workflow_id)

        results: list[VectorSearchResult] = []
        for embedding, similarity, final_score in reranked:
            content = self._resolve_entity_content(
                embedding, content_map
            )
            doc_name = doc_names.get(embedding.document_id, "unknown")

            # Extract page numbers from section extraction page_range
            page_numbers, page_range = self._extract_page_info(
                embedding, content_map
            )

            results.append(
                VectorSearchResult(
                    embedding_id=embedding.id,
                    document_id=embedding.document_id,
                    chunk_id=None,
                    canonical_entity_id=embedding.canonical_entity_id,
                    entity_id=embedding.entity_id,
                    content=content,
                    section_type=embedding.section_type,
                    entity_type=embedding.entity_type,
                    similarity_score=similarity,
                    final_score=final_score,
                    document_name=doc_name,
                    page_numbers=page_numbers,
                    page_range=page_range,
                    effective_date=embedding.effective_date,
                )
            )

        return results

    async def _resolve_document_names(
        self, document_ids: list[UUID]
    ) -> dict[UUID, str]:
        """Bulk-resolve document IDs to filenames."""
        if not document_ids:
            return {}

        stmt = select(Document.id, Document.file_path).where(
            Document.id.in_(document_ids)
        )
        result = await self.db_session.execute(stmt)

        return {
            row.id: Path(row.file_path).name
            for row in result
        }

    async def _resolve_content_map(
        self,
        section_keys: list[tuple[UUID, str]],
        workflow_id: UUID,
    ) -> dict[tuple[UUID, str], list]:
        """Bulk-fetch SectionExtraction records keyed by (document_id, section_type).

        Returns a map: (document_id, section_type) -> list[SectionExtraction]
        """
        content_map: dict[tuple[UUID, str], list] = {}

        for doc_id, section_type in section_keys:
            extractions = await self.section_repo.get_by_document(
                document_id=doc_id,
                section_type=section_type,
                workflow_id=workflow_id,
            )
            content_map[(doc_id, section_type)] = extractions

        return content_map

    def _resolve_entity_content(
        self,
        embedding: VectorEmbedding,
        content_map: dict[tuple[UUID, str], list],
    ) -> str:
        """Resolve the text content for a VectorEmbedding by reconstructing
        from SectionExtraction.extracted_fields using the VectorTemplateService.

        The entity_id format is "{section_type}_{entity_id_suffix}" (e.g.,
        "coverages_cov_0"). We look up the correct entity in extracted_fields
        using the section processor's entity indexing.
        """
        key = (embedding.document_id, embedding.section_type)
        extractions = content_map.get(key, [])

        if not extractions:
            return f"[{embedding.section_type}] {embedding.entity_type or 'entity'} (content unavailable)"

        # entity_id format: "{section_type}_{suffix}"
        # The suffix encodes position within the section (e.g., "cov_0", "exc_1")
        entity_id = embedding.entity_id or ""
        prefix = f"{embedding.section_type}_"
        suffix = entity_id[len(prefix):] if entity_id.startswith(prefix) else entity_id

        # Try to find the matching entity in extracted_fields
        for extraction in extractions:
            fields = extraction.extracted_fields or {}
            entity_data = self._find_entity_in_fields(fields, suffix, embedding.entity_type)
            if entity_data:
                # Use VectorTemplateService to reconstruct deterministic text
                try:
                    text = self.template_service.run_sync(
                        embedding.section_type, entity_data
                    ) if hasattr(self.template_service, 'run_sync') else self._format_entity_data(
                        embedding.section_type, entity_data
                    )
                    if text and len(text.strip()) >= 10:
                        return text
                except Exception:
                    pass

                # Fallback: format the entity data directly
                return self._format_entity_data(embedding.section_type, entity_data)

        # Last resort: return a summary from the first extraction
        return self._format_section_summary(extractions[0], embedding)

    def _find_entity_in_fields(
        self,
        fields: dict,
        suffix: str,
        entity_type: str | None,
    ) -> dict | None:
        """Find a specific entity within extracted_fields using the suffix.

        Extracted fields typically contain lists of entities keyed by type
        (e.g., {"coverages": [...], "exclusions": [...]}).
        The suffix often encodes the index (e.g., "cov_0" -> index 0).
        """
        # Try to parse index from suffix (e.g., "cov_0" -> 0, "exc_1" -> 1)
        parts = suffix.rsplit("_", 1)
        if len(parts) == 2:
            try:
                idx = int(parts[1])
            except ValueError:
                idx = None
        else:
            idx = None

        # Strategy 1: Look for lists in fields that match entity_type/section
        for key, value in fields.items():
            if isinstance(value, list) and value:
                if isinstance(value[0], dict):
                    if idx is not None and idx < len(value):
                        return value[idx]
                    # If no index, return first item as fallback
                    if idx is None and len(value) > 0:
                        return value[0]

        # Strategy 2: If fields itself is the entity data (flat dict)
        if idx is None or idx == 0:
            # Check if this looks like entity data (has string/number values)
            non_meta_keys = [k for k in fields if not k.startswith("_")]
            if non_meta_keys and not any(isinstance(fields[k], list) for k in non_meta_keys[:3]):
                return fields

        return None

    def _format_entity_data(self, section_type: str, data: dict) -> str:
        """Format entity data into readable text."""
        parts = [f"[{section_type}]"]
        for key, value in data.items():
            if key.startswith("_") or value is None:
                continue
            if isinstance(value, (dict, list)):
                continue
            parts.append(f"{key}: {value}")
        return " | ".join(parts) if len(parts) > 1 else parts[0]

    def _format_section_summary(self, extraction, embedding: VectorEmbedding) -> str:
        """Format a summary from section extraction as fallback content."""
        fields = extraction.extracted_fields or {}
        # Take first few key-value pairs as summary
        parts = [f"[{embedding.section_type}]"]
        count = 0
        for key, value in fields.items():
            if key.startswith("_") or value is None:
                continue
            if isinstance(value, list):
                parts.append(f"{key}: {len(value)} items")
            elif isinstance(value, dict):
                continue
            else:
                parts.append(f"{key}: {value}")
            count += 1
            if count >= 5:
                break
        return " | ".join(parts) if len(parts) > 1 else f"[{embedding.section_type}] (summary)"

    def _extract_page_info(
        self,
        embedding: VectorEmbedding,
        content_map: dict[tuple[UUID, str], list],
    ) -> tuple[list[int], dict[str, int] | None]:
        """Extract page_numbers and page_range from SectionExtraction metadata."""
        key = (embedding.document_id, embedding.section_type)
        extractions = content_map.get(key, [])

        for extraction in extractions:
            page_range = extraction.page_range
            if page_range and isinstance(page_range, dict):
                start = page_range.get("start")
                end = page_range.get("end")
                if start is not None and end is not None:
                    page_numbers = list(range(int(start), int(end) + 1))
                    return page_numbers, {"start": int(start), "end": int(end)}

        return [], None
