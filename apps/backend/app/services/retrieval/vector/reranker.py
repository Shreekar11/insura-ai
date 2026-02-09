"""
Intent-Aware Reranking for Vector Search Results

Applies domain-specific boosts to raw vector search results:
1. Section-type boost: Prioritizes sections relevant to the intent
2. Entity-match boost: Rewards results matching extracted entities
3. Recency boost: Favors recent policy data based on effective_date
"""

from datetime import date, timedelta

from app.database.models import VectorEmbedding
from app.schemas.query import ExtractedQueryEntities
from app.services.retrieval.constants import (
    ENTITY_MATCH_BOOST,
    INTENT_SECTION_BOOSTS,
    RECENCY_BOOST_MAX,
    RECENCY_DECAY_DAYS,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class IntentReranker:
    """Reranks vector search results using intent-aware boosting signals."""

    def rerank(
        self,
        results: list[tuple[VectorEmbedding, float]],
        intent: str,
        extracted_entities: ExtractedQueryEntities,
        entity_type_filters: list[str] | None = None,
    ) -> list[tuple[VectorEmbedding, float, float]]:
        """
        Rerank search results with intent-aware boosting.

        Args:
            results: List of (VectorEmbedding, cosine_distance) tuples from search
            intent: Query intent (QA, ANALYSIS, AUDIT)
            extracted_entities: Entities extracted from the query
            entity_type_filters: Optional entity type filters from query plan

        Returns:
            List of (VectorEmbedding, similarity_score, final_score) tuples,
            sorted by final_score descending
        """
        if not results:
            return []

        section_boosts = INTENT_SECTION_BOOSTS.get(intent, {})

        reranked = []
        for embedding, distance in results:
            # Base similarity score: convert cosine distance (0=identical, 2=opposite)
            # to similarity (1=identical, 0=opposite)
            similarity = max(0.0, 1.0 - distance)

            # 1. Section-type boost
            section_boost = section_boosts.get(embedding.section_type, 0.0)

            # 2. Entity-match boost
            entity_boost = self._compute_entity_boost(
                embedding, extracted_entities, entity_type_filters
            )

            # 3. Recency boost
            recency_boost = self._compute_recency_boost(embedding.effective_date)

            # Combine: additive boosts on top of base similarity
            final_score = similarity + section_boost + entity_boost + recency_boost

            reranked.append((embedding, similarity, final_score))

        # Sort by final_score descending (highest first)
        reranked.sort(key=lambda x: x[2], reverse=True)

        LOGGER.info(
            "Reranking complete",
            extra={
                "intent": intent,
                "total_results": len(reranked),
                "top_score": reranked[0][2] if reranked else 0.0,
                "bottom_score": reranked[-1][2] if reranked else 0.0,
            },
        )

        return reranked

    def _compute_entity_boost(
        self,
        embedding: VectorEmbedding,
        extracted_entities: ExtractedQueryEntities,
        entity_type_filters: list[str] | None,
    ) -> float:
        """Compute entity-match boost based on extracted entities."""
        boost = 0.0

        # Boost if entity_type matches query-derived filters
        if entity_type_filters and embedding.entity_type:
            if embedding.entity_type.lower() in [f.lower() for f in entity_type_filters]:
                boost += ENTITY_MATCH_BOOST

        # Boost if coverage type matches extracted coverage types
        if extracted_entities.coverage_types and embedding.entity_type:
            if embedding.entity_type.lower() in ["coverage", "coverages"]:
                boost += ENTITY_MATCH_BOOST * 0.5

        return boost

    def _compute_recency_boost(self, effective_date: date | None) -> float:
        """Compute recency boost based on effective_date proximity."""
        if not effective_date:
            return 0.0

        today = date.today()
        days_diff = abs((today - effective_date).days)

        if days_diff >= RECENCY_DECAY_DAYS:
            return 0.0

        # Linear decay: full boost at 0 days, zero boost at RECENCY_DECAY_DAYS
        decay_factor = 1.0 - (days_diff / RECENCY_DECAY_DAYS)
        return RECENCY_BOOST_MAX * decay_factor
