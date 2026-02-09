"""Unit tests for IntentReranker.

Tests:
- Section-type boost based on intent
- Entity-match boost based on extracted entities
- Recency boost based on effective_date
- Combined scoring and sorting
- Edge cases (empty results, missing fields)
"""

from datetime import date, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.query import ExtractedQueryEntities
from app.services.retrieval.constants import (
    ENTITY_MATCH_BOOST,
    INTENT_SECTION_BOOSTS,
    RECENCY_BOOST_MAX,
    RECENCY_DECAY_DAYS,
)
from app.services.retrieval.vector.reranker import IntentReranker


def _make_embedding(
    section_type: str = "coverages",
    entity_type: str | None = "coverage",
    effective_date: date | None = None,
) -> MagicMock:
    """Create a mock VectorEmbedding with specified attributes."""
    emb = MagicMock()
    emb.section_type = section_type
    emb.entity_type = entity_type
    emb.effective_date = effective_date
    return emb


def _make_entities(**kwargs) -> ExtractedQueryEntities:
    """Create ExtractedQueryEntities with defaults."""
    return ExtractedQueryEntities(**kwargs)


class TestIntentReranker:
    """Tests for IntentReranker.rerank()."""

    def setup_method(self):
        self.reranker = IntentReranker()
        self.default_entities = _make_entities()

    # ------------------------------------------------------------------ #
    # Empty / trivial
    # ------------------------------------------------------------------ #

    def test_empty_results_returns_empty(self):
        result = self.reranker.rerank([], "QA", self.default_entities)
        assert result == []

    def test_single_result_returns_one(self):
        emb = _make_embedding()
        results = [(emb, 0.3)]  # distance 0.3 -> similarity 0.7
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        assert len(reranked) == 1
        assert reranked[0][0] is emb

    # ------------------------------------------------------------------ #
    # Base similarity conversion
    # ------------------------------------------------------------------ #

    def test_distance_to_similarity_conversion(self):
        """Distance 0 -> similarity 1.0, distance 1 -> similarity 0.0."""
        emb_close = _make_embedding(section_type="unknown")
        emb_far = _make_embedding(section_type="unknown")

        results = [(emb_close, 0.0), (emb_far, 1.0)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)

        # emb_close has similarity 1.0, emb_far has similarity 0.0
        close_entry = next(r for r in reranked if r[0] is emb_close)
        far_entry = next(r for r in reranked if r[0] is emb_far)

        assert close_entry[1] == pytest.approx(1.0)
        assert far_entry[1] == pytest.approx(0.0)
        assert close_entry[2] > far_entry[2]

    def test_distance_clamp_negative_similarity(self):
        """Distance > 1.0 should not produce negative similarity."""
        emb = _make_embedding(section_type="unknown")
        results = [(emb, 1.5)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        assert reranked[0][1] == pytest.approx(0.0)

    # ------------------------------------------------------------------ #
    # Section-type boost
    # ------------------------------------------------------------------ #

    def test_section_boost_qa_declarations(self):
        """Declarations section should get a boost for QA intent."""
        emb_dec = _make_embedding(section_type="declarations")
        emb_other = _make_embedding(section_type="unknown")

        # Same distance, section boost should differentiate
        results = [(emb_dec, 0.3), (emb_other, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)

        dec_entry = next(r for r in reranked if r[0] is emb_dec)
        other_entry = next(r for r in reranked if r[0] is emb_other)

        expected_boost = INTENT_SECTION_BOOSTS["QA"]["declarations"]
        assert dec_entry[2] > other_entry[2]
        assert dec_entry[2] - other_entry[2] == pytest.approx(expected_boost, abs=0.01)

    def test_section_boost_analysis_coverages(self):
        """Coverages section should get highest boost for ANALYSIS intent."""
        emb_cov = _make_embedding(section_type="coverages")
        emb_end = _make_embedding(section_type="endorsements")

        results = [(emb_cov, 0.3), (emb_end, 0.3)]
        reranked = self.reranker.rerank(results, "ANALYSIS", self.default_entities)

        cov_entry = next(r for r in reranked if r[0] is emb_cov)
        end_entry = next(r for r in reranked if r[0] is emb_end)

        cov_boost = INTENT_SECTION_BOOSTS["ANALYSIS"]["coverages"]
        end_boost = INTENT_SECTION_BOOSTS["ANALYSIS"]["endorsements"]
        assert cov_boost > end_boost
        assert cov_entry[2] > end_entry[2]

    def test_section_boost_unknown_intent_no_boost(self):
        """Unknown intent should produce zero section boost."""
        emb = _make_embedding(section_type="coverages")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(results, "UNKNOWN", self.default_entities)
        # Only base similarity, no section boost
        assert reranked[0][1] == pytest.approx(0.7)
        assert reranked[0][2] == pytest.approx(0.7)

    # ------------------------------------------------------------------ #
    # Entity-match boost
    # ------------------------------------------------------------------ #

    def test_entity_type_filter_match_boost(self):
        """Entity type matching query filters should get a boost."""
        emb_match = _make_embedding(entity_type="coverage")
        emb_no_match = _make_embedding(entity_type="exclusion")

        results = [(emb_match, 0.3), (emb_no_match, 0.3)]
        reranked = self.reranker.rerank(
            results,
            "QA",
            self.default_entities,
            entity_type_filters=["coverage"],
        )

        match_entry = next(r for r in reranked if r[0] is emb_match)
        no_match_entry = next(r for r in reranked if r[0] is emb_no_match)

        assert match_entry[2] > no_match_entry[2]

    def test_entity_type_filter_case_insensitive(self):
        """Entity type matching should be case-insensitive."""
        emb = _make_embedding(entity_type="Coverage")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(
            results, "QA", self.default_entities, entity_type_filters=["coverage"]
        )
        # Should get the entity match boost
        base_sim = 0.7
        section_boost = INTENT_SECTION_BOOSTS["QA"].get("coverages", 0.0)
        expected_min = base_sim + section_boost + ENTITY_MATCH_BOOST
        assert reranked[0][2] >= expected_min - 0.01

    def test_coverage_type_entity_boost(self):
        """Coverage entities should get extra boost when coverage types extracted."""
        entities_with_coverage = _make_entities(coverage_types=["general liability"])
        emb_cov = _make_embedding(entity_type="coverage")
        emb_other = _make_embedding(entity_type="exclusion")

        results = [(emb_cov, 0.3), (emb_other, 0.3)]
        reranked = self.reranker.rerank(results, "QA", entities_with_coverage)

        cov_entry = next(r for r in reranked if r[0] is emb_cov)
        other_entry = next(r for r in reranked if r[0] is emb_other)

        # Coverage entity gets the 0.5 * ENTITY_MATCH_BOOST boost
        assert cov_entry[2] > other_entry[2]

    def test_no_entity_filters_no_boost(self):
        """No entity type filters should produce zero entity boost."""
        emb = _make_embedding(entity_type="coverage", section_type="unknown")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        assert reranked[0][1] == pytest.approx(0.7)
        # Final score = base similarity only (no section, no entity, no recency)
        assert reranked[0][2] == pytest.approx(0.7)

    def test_entity_type_none_no_crash(self):
        """Embedding with entity_type=None should not crash."""
        emb = _make_embedding(entity_type=None, section_type="unknown")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(
            results, "QA", self.default_entities, entity_type_filters=["coverage"]
        )
        assert len(reranked) == 1

    # ------------------------------------------------------------------ #
    # Recency boost
    # ------------------------------------------------------------------ #

    def test_recency_boost_today(self):
        """Effective date today should get maximum recency boost."""
        emb = _make_embedding(effective_date=date.today(), section_type="unknown")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        # final_score = base (0.7) + recency (RECENCY_BOOST_MAX)
        assert reranked[0][2] == pytest.approx(0.7 + RECENCY_BOOST_MAX, abs=0.01)

    def test_recency_boost_half_decay(self):
        """Effective date at half the decay period should get ~50% of max boost."""
        half_days = RECENCY_DECAY_DAYS // 2
        eff_date = date.today() - timedelta(days=half_days)
        emb = _make_embedding(effective_date=eff_date, section_type="unknown")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        expected_boost = RECENCY_BOOST_MAX * (1.0 - half_days / RECENCY_DECAY_DAYS)
        assert reranked[0][2] == pytest.approx(0.7 + expected_boost, abs=0.01)

    def test_recency_boost_expired(self):
        """Effective date beyond decay period should get zero recency boost."""
        old_date = date.today() - timedelta(days=RECENCY_DECAY_DAYS + 100)
        emb = _make_embedding(effective_date=old_date, section_type="unknown")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        assert reranked[0][2] == pytest.approx(0.7)

    def test_recency_boost_no_date(self):
        """Missing effective_date should produce zero recency boost."""
        emb = _make_embedding(effective_date=None, section_type="unknown")
        results = [(emb, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)
        assert reranked[0][2] == pytest.approx(0.7)

    # ------------------------------------------------------------------ #
    # Combined scoring and sort order
    # ------------------------------------------------------------------ #

    def test_results_sorted_by_final_score_descending(self):
        """Results should be sorted by final_score highest first."""
        emb_a = _make_embedding(section_type="declarations")  # gets boost
        emb_b = _make_embedding(section_type="unknown")

        results = [(emb_a, 0.5), (emb_b, 0.3)]  # b has better distance
        reranked = self.reranker.rerank(results, "QA", self.default_entities)

        scores = [r[2] for r in reranked]
        assert scores == sorted(scores, reverse=True)

    def test_combined_boosts_accumulate(self):
        """Section + entity + recency boosts should all accumulate."""
        emb = _make_embedding(
            section_type="declarations",
            entity_type="coverage",
            effective_date=date.today(),
        )
        entities = _make_entities(coverage_types=["property"])
        results = [(emb, 0.3)]

        reranked = self.reranker.rerank(
            results, "QA", entities, entity_type_filters=["coverage"]
        )

        base = 0.7
        section_boost = INTENT_SECTION_BOOSTS["QA"]["declarations"]
        entity_boost = ENTITY_MATCH_BOOST + ENTITY_MATCH_BOOST * 0.5  # filter + coverage type
        recency_boost = RECENCY_BOOST_MAX

        expected = base + section_boost + entity_boost + recency_boost
        assert reranked[0][2] == pytest.approx(expected, abs=0.01)

    def test_multiple_results_ordering(self):
        """Multiple results with varying boosts should be correctly ordered."""
        emb_high = _make_embedding(
            section_type="declarations", effective_date=date.today()
        )
        emb_mid = _make_embedding(section_type="coverages")
        emb_low = _make_embedding(section_type="unknown")

        # All same distance
        results = [(emb_high, 0.3), (emb_mid, 0.3), (emb_low, 0.3)]
        reranked = self.reranker.rerank(results, "QA", self.default_entities)

        assert reranked[0][0] is emb_high
        assert reranked[1][0] is emb_mid
        assert reranked[2][0] is emb_low
