"""Semantic citation resolution service.

Implements a tiered approach to resolve extracted text to PDF coordinates:
- Tier 1: Direct text match via CitationMapper (word-level fuzzy matching)
- Tier 2: Semantic chunk search via chunk embeddings (cosine similarity)
- Tier 3: Placeholder fallback (full-page bounding boxes)

Usage:
    resolver = CitationResolutionService(session, citation_mapper)
    result = await resolver.resolve(source_text, document_id, expected_page=3)
    # result.spans -> List[CitationSpan]
    # result.method -> "direct_text_match" | "semantic_chunk_match" | "placeholder"
"""

from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.schemas.citation import BoundingBox, CitationSpan
from app.services.citation.citation_mapper import CitationMapper
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
SEMANTIC_MAX_DISTANCE = 0.65
SEMANTIC_TOP_K = 3


@dataclass
class ResolutionResult:
    """Result of citation resolution."""

    spans: List[CitationSpan]
    method: str  # "direct_text_match", "semantic_chunk_match", "placeholder"
    confidence: float = 0.0
    matched_chunk_id: Optional[UUID] = None
    semantic_distance: Optional[float] = None


class CitationResolutionService:
    """Resolves source text to PDF coordinates using tiered approach.

    Tier 1 (Direct Match):
        Uses CitationMapper's sliding-window fuzzy match against word-level
        coordinates from pdfplumber. Fast and precise when text exists verbatim.

    Tier 2 (Semantic Search):
        Embeds the source text with all-MiniLM-L6-v2, searches chunk embeddings
        via pgvector cosine distance. Returns the best matching chunk's page.
        Then retries CitationMapper on that page with a lower threshold.

    Tier 3 (Placeholder):
        Falls back to full-page bounding boxes when no match is found.
    """

    _shared_model: Optional[SentenceTransformer] = None

    def __init__(
        self,
        session: AsyncSession,
        citation_mapper: Optional[CitationMapper] = None,
    ):
        self.session = session
        self.citation_mapper = citation_mapper
        self.vector_repo = VectorEmbeddingRepository(session)

    @classmethod
    def _get_model(cls) -> SentenceTransformer:
        if cls._shared_model is None:
            LOGGER.info(f"Loading embedding model for citation resolution: {EMBEDDING_MODEL}")
            cls._shared_model = SentenceTransformer(EMBEDDING_MODEL)
        return cls._shared_model

    async def resolve(
        self,
        source_text: str,
        document_id: UUID,
        expected_page: Optional[int] = None,
        page_numbers: Optional[List[int]] = None,
    ) -> ResolutionResult:
        """Resolve source text to PDF coordinates.

        Args:
            source_text: Verbatim text to locate in the document
            document_id: Document UUID
            expected_page: Hint for starting page search
            page_numbers: Known page numbers for the item

        Returns:
            ResolutionResult with spans and the method used
        """
        primary_page = expected_page or (min(page_numbers) if page_numbers else 1)
        all_pages = page_numbers or [primary_page]

        # Tier 1: Direct text match
        result = self._try_direct_match(source_text, primary_page)
        if result:
            LOGGER.info(
                "[RESOLUTION] Tier 1 (direct text match) succeeded",
                extra={
                    "document_id": str(document_id),
                    "page": result.spans[0].page_number if result.spans else primary_page,
                    "confidence": result.confidence,
                },
            )
            return result

        # Tier 2: Semantic chunk search
        result = await self._try_semantic_search(
            source_text, document_id, primary_page
        )
        if result:
            LOGGER.info(
                "[RESOLUTION] Tier 2 (semantic chunk match) succeeded",
                extra={
                    "document_id": str(document_id),
                    "matched_chunk_id": str(result.matched_chunk_id) if result.matched_chunk_id else None,
                    "distance": result.semantic_distance,
                    "confidence": result.confidence,
                },
            )
            return result

        # Tier 3: Placeholder fallback
        LOGGER.info(
            "[RESOLUTION] Falling back to Tier 3 (placeholder)",
            extra={
                "document_id": str(document_id),
                "page": primary_page,
                "text_length": len(source_text) if source_text else 0,
            },
        )
        return self._build_placeholder(all_pages, source_text)

    # ------------------------------------------------------------------
    # Tier 1: Direct text match
    # ------------------------------------------------------------------

    def _try_direct_match(
        self, source_text: str, expected_page: int
    ) -> Optional[ResolutionResult]:
        if not self.citation_mapper or not source_text:
            return None

        search_text = source_text[:500] if len(source_text) > 500 else source_text

        match = self.citation_mapper.find_text_location(
            search_text=search_text,
            expected_page=expected_page,
            fuzzy_threshold=0.75,
        )

        if match and match.spans:
            return ResolutionResult(
                spans=match.spans,
                method="direct_text_match",
                confidence=match.confidence,
            )
        return None

    # ------------------------------------------------------------------
    # Tier 2: Semantic chunk search
    # ------------------------------------------------------------------

    async def _try_semantic_search(
        self,
        source_text: str,
        document_id: UUID,
        primary_page: int,
    ) -> Optional[ResolutionResult]:
        if not source_text or len(source_text.strip()) < 20:
            return None

        try:
            model = self._get_model()
            query_embedding = model.encode(
                source_text[:1000], show_progress_bar=False
            ).tolist()

            results = await self.vector_repo.search_chunk_embeddings(
                embedding=query_embedding,
                document_id=document_id,
                top_k=SEMANTIC_TOP_K,
                max_distance=SEMANTIC_MAX_DISTANCE,
            )

            if not results:
                LOGGER.debug(
                    "[RESOLUTION] No chunk embeddings within threshold",
                    extra={
                        "document_id": str(document_id),
                        "threshold": SEMANTIC_MAX_DISTANCE,
                    },
                )
                return None

            best_embedding, best_distance = results[0]

            chunk = await self._load_chunk(best_embedding.source_chunk_id)
            if not chunk:
                LOGGER.warning(
                    "[RESOLUTION] Could not load source chunk",
                    extra={"source_chunk_id": str(best_embedding.source_chunk_id)},
                )
                return None

            confidence = max(0.0, min(1.0, 1.0 - best_distance))

            # Try narrowed direct match on the chunk's page.
            if self.citation_mapper:
                search_text = source_text[:500] if len(source_text) > 500 else source_text
                match = self.citation_mapper.find_text_location(
                    search_text=search_text,
                    expected_page=chunk.page_number,
                    fuzzy_threshold=0.6,
                )
                if match and match.spans:
                    return ResolutionResult(
                        spans=match.spans,
                        method="semantic_chunk_match",
                        confidence=confidence,
                        matched_chunk_id=chunk.id,
                        semantic_distance=best_distance,
                    )

            # Chunk matched semantically but no precise bbox — use chunk's page
            span = CitationSpan(
                page_number=chunk.page_number,
                bounding_boxes=[BoundingBox(x0=0.0, y0=0.0, x1=612.0, y1=792.0)],
                text_content=source_text[:1000],
            )
            return ResolutionResult(
                spans=[span],
                method="semantic_chunk_match",
                confidence=confidence,
                matched_chunk_id=chunk.id,
                semantic_distance=best_distance,
            )

        except Exception as e:
            LOGGER.warning(
                f"[RESOLUTION] Semantic search failed: {e}",
                extra={"document_id": str(document_id)},
            )
            return None

    async def _load_chunk(self, chunk_id: Optional[UUID]) -> Optional[DocumentChunk]:
        if not chunk_id:
            return None
        result = await self.session.execute(
            select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Tier 3: Placeholder fallback
    # ------------------------------------------------------------------

    def _build_placeholder(
        self, page_numbers: List[int], source_text: str
    ) -> ResolutionResult:
        primary_page = min(page_numbers) if page_numbers else 1
        placeholder_box = BoundingBox(x0=0.0, y0=0.0, x1=612.0, y1=792.0)

        spans = [
            CitationSpan(
                page_number=primary_page,
                bounding_boxes=[placeholder_box],
                text_content=source_text[:1000] if source_text else "",
            )
        ]

        for page_num in page_numbers[1:]:
            spans.append(
                CitationSpan(
                    page_number=page_num,
                    bounding_boxes=[placeholder_box],
                    text_content="[continued]",
                )
            )

        return ResolutionResult(
            spans=spans,
            method="placeholder",
            confidence=0.0,
        )


__all__ = [
    "CitationResolutionService",
    "ResolutionResult",
]
