"""Chunk-level embedding service for semantic citation resolution.

Generates embeddings for document chunks (from hybrid chunking) to enable
semantic similarity search between extracted item summaries and source chunks.
This powers the Tier 2 citation fallback when direct text matching fails.

Uses the same embedding model (all-MiniLM-L6-v2, 384-dim) as the entity-level
embeddings for consistency.
"""

import hashlib
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ChunkEmbeddingService:
    """Service for generating chunk-level vector embeddings.

    Embeds document chunks for semantic citation resolution. Each chunk's
    contextualized text (with section header) is embedded using the same
    model as entity-level embeddings.

    Chunk embeddings are stored in the shared vector_embeddings table with:
    - entity_type = "chunk"
    - entity_id = stable_chunk_id (e.g., "doc_{uuid}_p5_c0")
    - source_chunk_id = FK to document_chunks.id
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def __init__(self, session: AsyncSession):
        self.session = session
        self.vector_repo = VectorEmbeddingRepository(session)
        self._model = None

    @property
    def model(self):
        """Lazy loader for the SentenceTransformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            LOGGER.info(f"Loading embedding model: {self.MODEL_NAME}")
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    async def generate_chunk_embeddings(
        self,
        document_id: UUID,
        workflow_id: UUID,
    ) -> Dict[str, Any]:
        """Generate embeddings for all chunks of a document.

        Args:
            document_id: Document UUID
            workflow_id: Workflow UUID for provenance

        Returns:
            Dict with processing statistics
        """
        LOGGER.info(
            "Starting chunk embedding generation",
            extra={
                "document_id": str(document_id),
                "workflow_id": str(workflow_id),
            }
        )

        # Delete existing chunk embeddings for this document (avoid duplicates on re-run)
        await self._delete_existing_chunk_embeddings(document_id)

        # Fetch all chunks for the document
        chunks = await self._fetch_chunks(document_id)

        if not chunks:
            LOGGER.info(
                "No chunks found for embedding generation",
                extra={"document_id": str(document_id)},
            )
            return {
                "chunks_embedded": 0,
                "status": "no_chunks",
            }

        # Generate embeddings in batch for efficiency
        embeddings_created = await self._embed_chunks_batch(
            chunks, document_id, workflow_id
        )

        await self.session.commit()

        LOGGER.info(
            f"Chunk embedding generation complete: {embeddings_created}/{len(chunks)} embedded",
            extra={
                "document_id": str(document_id),
                "chunks_embedded": embeddings_created,
                "total_chunks": len(chunks),
            }
        )

        return {
            "chunks_embedded": embeddings_created,
            "total_chunks": len(chunks),
            "status": "completed",
            "model": self.MODEL_NAME,
        }

    async def _fetch_chunks(self, document_id: UUID) -> List[DocumentChunk]:
        """Fetch all document chunks ordered by page and index."""
        result = await self.session.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def _delete_existing_chunk_embeddings(self, document_id: UUID) -> int:
        """Delete existing chunk-type embeddings for a document."""
        from sqlalchemy import delete
        from app.database.models import VectorEmbedding

        query = (
            delete(VectorEmbedding)
            .where(VectorEmbedding.document_id == document_id)
            .where(VectorEmbedding.entity_type == "chunk")
        )
        result = await self.session.execute(query)
        await self.session.flush()

        deleted = result.rowcount
        if deleted > 0:
            LOGGER.info(
                f"Deleted {deleted} existing chunk embeddings",
                extra={"document_id": str(document_id)},
            )
        return deleted

    async def _embed_chunks_batch(
        self,
        chunks: List[DocumentChunk],
        document_id: UUID,
        workflow_id: UUID,
    ) -> int:
        """Embed all chunks using batch encoding for efficiency.

        Args:
            chunks: List of DocumentChunk records
            document_id: Document UUID
            workflow_id: Workflow UUID

        Returns:
            Number of embeddings created
        """
        # Prepare texts for batch encoding
        texts = []
        valid_chunks = []

        for chunk in chunks:
            text = self._get_embedding_text(chunk)
            if text and len(text.strip()) >= 10:
                texts.append(text)
                valid_chunks.append(chunk)

        if not texts:
            return 0

        # Batch encode all texts at once (much faster than one-by-one)
        LOGGER.info(
            f"Batch encoding {len(texts)} chunk texts",
            extra={"document_id": str(document_id)},
        )
        vectors = self.model.encode(texts, show_progress_bar=False).tolist()

        # Store each embedding
        embeddings_created = 0
        for chunk, text, vector in zip(valid_chunks, texts, vectors):
            try:
                content_hash = hashlib.sha256(text.encode()).hexdigest()
                entity_id = chunk.stable_chunk_id or f"chunk_{chunk.id}"

                await self.vector_repo.create(
                    document_id=document_id,
                    workflow_id=workflow_id,
                    source_chunk_id=chunk.id,
                    section_type=chunk.effective_section_type or chunk.section_type or "unknown",
                    entity_type="chunk",
                    entity_id=entity_id,
                    embedding_model=self.MODEL_NAME,
                    embedding_dim=self.EMBEDDING_DIM,
                    embedding_version="v1",
                    embedding=vector,
                    content_hash=content_hash,
                    status="EMBEDDED",
                    embedded_at=datetime.now(timezone.utc),
                )
                embeddings_created += 1
            except Exception as e:
                LOGGER.warning(
                    f"Failed to embed chunk {chunk.id}: {e}",
                    extra={
                        "chunk_id": str(chunk.id),
                        "stable_chunk_id": chunk.stable_chunk_id,
                    },
                )

        return embeddings_created

    def _get_embedding_text(self, chunk: DocumentChunk) -> str:
        """Get the best text representation for embedding a chunk.

        Prefers contextualized text (with section header) over raw text.
        """
        # Check if contextualized_text is stored in additional_metadata
        # (saved by SectionChunkRepository.create_hybrid_chunk)
        if chunk.raw_text:
            # Build a context-enriched version with section info
            parts = []

            # Add section context header
            section = chunk.effective_section_type or chunk.section_type
            if section:
                page_info = f"Page {chunk.page_number}"
                parts.append(f"{section.replace('_', ' ').title()} ({page_info})")

            parts.append(chunk.raw_text)
            return "\n\n".join(parts)

        return ""
