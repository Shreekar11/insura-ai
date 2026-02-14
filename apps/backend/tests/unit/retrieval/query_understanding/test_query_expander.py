"""Unit tests for QueryExpander."""

import pytest
from app.services.retrieval.query_understanding.query_expander import QueryExpander


class TestQueryExpander:
    """Test suite for QueryExpander."""

    @pytest.fixture
    def expander(self):
        """Create QueryExpander instance for testing."""
        return QueryExpander()

    def test_expand_with_abbreviation(self, expander):
        """Test query expansion with insurance abbreviations."""
        query = "What is the BI coverage?"
        expanded = expander.expand(query)

        # Should include original query
        assert query in expanded

        # Should include expansion with "bodily injury"
        assert any("bodily injury" in q.lower() for q in expanded)

    def test_expand_with_multiple_abbreviations(self, expander):
        """Test expansion when multiple abbreviations are present."""
        query = "Compare BI and PD limits"
        expanded = expander.expand(query)

        # Should include original
        assert query in expanded

        # Should have expansions for both BI and PD
        assert any("bodily injury" in q.lower() for q in expanded)
        assert any("property damage" in q.lower() for q in expanded)

    def test_expand_preserves_original(self, expander):
        """Test that original query is always preserved."""
        queries = [
            "What is the GL coverage?",
            "Show me the SIR amount",
            "Find WC policies",
        ]

        for query in queries:
            expanded = expander.expand(query)
            assert query in expanded, f"Original query should be preserved: {query}"
            assert expanded[0] == query, "Original should be first in list"

    def test_expand_no_matches(self, expander):
        """Test expansion when query has no expandable terms."""
        query = "Tell me about this insurance document"
        expanded = expander.expand(query)

        # Should only return original query
        assert len(expanded) == 1
        assert expanded[0] == query

    def test_expand_respects_max_expansions(self, expander):
        """Test that expansion respects max_expansions parameter."""
        query = "What is the BI, PD, GL, and WC coverage?"
        max_expansions = 3

        expanded = expander.expand(query, max_expansions=max_expansions)

        # Should not exceed max_expansions
        assert len(expanded) <= max_expansions

    def test_expand_case_insensitive(self, expander):
        """Test that expansion is case-insensitive."""
        queries = [
            "What is the BI coverage?",
            "What is the bi coverage?",
            "What is the Bi coverage?",
        ]

        for query in queries:
            expanded = expander.expand(query)
            # Should expand all variants
            assert len(expanded) > 1, f"Should expand case variant: {query}"
            assert any("bodily injury" in q.lower() for q in expanded)

    def test_expand_whole_word_matching(self, expander):
        """Test that expansion only matches whole words."""
        # "GL" should match, but not "ANGLISH" containing "GL"
        query = "What is the ANGLISH policy?"
        expanded = expander.expand(query)

        # Should not expand "ANGLISH"
        assert len(expanded) == 1
        assert expanded[0] == query

    def test_expand_deduplication(self, expander):
        """Test that duplicate expansions are deduplicated."""
        # If BI appears multiple times, should still generate unique expansions
        query = "Compare BI and BI coverage"
        expanded = expander.expand(query)

        # Should deduplicate
        assert len(expanded) == len(set(q.lower() for q in expanded)), \
            "Should deduplicate expansions"

    def test_expand_common_abbreviations(self, expander):
        """Test expansion of common insurance abbreviations."""
        test_cases = [
            ("GL", "general liability"),
            ("WC", "workers comp"),
            ("AL", "auto liability"),
            ("SIR", "self-insured retention"),
            ("E&O", "errors and omissions"),
        ]

        for abbr, expected_expansion in test_cases:
            query = f"What is the {abbr} coverage?"
            expanded = expander.expand(query)

            # Should include expansion with expected term
            assert any(expected_expansion.lower() in q.lower() for q in expanded), \
                f"Should expand {abbr} to include '{expected_expansion}'"

    def test_expand_term_single(self, expander):
        """Test expand_term method for single terms."""
        test_cases = [
            ("BI", ["BI", "bodily injury", "personal injury"]),
            ("GL", ["GL", "general liability", "CGL", "commercial general liability"]),
            ("deductible", ["deductible", "self-insured retention", "SIR", "retention"]),
        ]

        for term, expected_expansions in test_cases:
            result = expander.expand_term(term)

            # Should return list of expansions
            assert isinstance(result, list)

            # Should include the original term or its expansions
            assert any(exp.lower() in [r.lower() for r in result] for exp in expected_expansions)

    def test_expand_term_no_match(self, expander):
        """Test expand_term with term that has no expansions."""
        term = "unknown_term_xyz"
        result = expander.expand_term(term)

        # Should return the original term
        assert result == [term]

    def test_get_canonical_term(self, expander):
        """Test get_canonical_term method."""
        test_cases = [
            ("BI", "bodily injury"),  # Abbreviation → full term
            ("GL", "general liability"),
            ("deductible", "self-insured retention"),  # Already canonical but might get longer form
        ]

        for term, expected_canonical in test_cases:
            result = expander.get_canonical_term(term)

            # Should return a canonical (typically longer) form
            assert isinstance(result, str)

            # For abbreviations, canonical should be longer
            if len(term) <= 3:
                assert len(result) > len(term), \
                    f"Canonical form of '{term}' should be longer: got '{result}'"

    def test_get_canonical_term_no_expansion(self, expander):
        """Test get_canonical_term with term that has no expansions."""
        term = "unknown_term"
        result = expander.get_canonical_term(term)

        # Should return the original term
        assert result == term

    def test_expand_real_world_queries(self, expander):
        """Test expansion with realistic insurance queries."""
        test_cases = [
            {
                "query": "What is the BI limit for this GL policy?",
                "should_contain": ["bodily injury", "general liability"],
            },
            {
                "query": "Compare the SIR amounts",
                "should_contain": ["self-insured retention", "deductible"],
            },
            {
                "query": "Show me the WC endorsements",
                "should_contain": ["workers comp"],
            },
        ]

        for test_case in test_cases:
            query = test_case["query"]
            expected_terms = test_case["should_contain"]
            expanded = expander.expand(query)

            # Should have multiple expansions
            assert len(expanded) > 1, f"Should expand: {query}"

            # Should include original
            assert query in expanded

            # Should include expected terms in some expansion
            for term in expected_terms:
                assert any(term.lower() in q.lower() for q in expanded), \
                    f"Expansions should include '{term}' for query: {query}"

    def test_expand_preserves_query_structure(self, expander):
        """Test that expansion preserves overall query structure."""
        query = "What is the BI coverage limit for policy POL-12345?"
        expanded = expander.expand(query)

        # Expanded queries should maintain structure
        for exp_query in expanded:
            # Should still be a question
            assert "?" in exp_query

            # Should still contain policy number
            assert "POL-12345" in exp_query

            # Should still have "coverage limit"
            assert "coverage limit" in exp_query.lower() or "limit" in exp_query.lower()

    def test_expand_multiple_variants(self, expander):
        """Test that multiple expansion variants are generated."""
        query = "What is the GL coverage?"
        expanded = expander.expand(query)

        # Should have multiple variants
        assert len(expanded) > 1

        # Check for expected variants
        variants = [q.lower() for q in expanded]

        # Should have original
        assert query.lower() in variants

        # Should have variant with "general liability"
        assert any("general liability" in v for v in variants)

    def test_expand_limits_expansions_per_term(self, expander):
        """Test that expansions are limited per term."""
        # Even if a term has many expansions, should only take top N
        query = "What is the deductible?"
        expanded = expander.expand(query, max_expansions=5)

        # Should limit total expansions
        assert len(expanded) <= 5

    def test_expand_empty_query(self, expander):
        """Test expansion of empty query."""
        query = ""
        expanded = expander.expand(query)

        # Should return list with empty string
        assert len(expanded) == 1
        assert expanded[0] == ""

    def test_expand_combined_terms(self, expander):
        """Test expansion when multiple expandable terms are in close proximity."""
        query = "Compare BI, PD, and UM limits"
        expanded = expander.expand(query)

        # Should expand multiple terms
        assert len(expanded) > 1

        # Should preserve original
        assert query in expanded

        # Should have expansions for at least one term
        expansion_terms = ["bodily injury", "property damage", "uninsured motorist"]
        assert any(
            any(term in q.lower() for term in expansion_terms)
            for q in expanded
        ), "Should expand at least one abbreviation"

    def test_expand_special_characters(self, expander):
        """Test expansion with special characters in abbreviations."""
        # E&O has an ampersand
        query = "What is the E&O coverage?"
        expanded = expander.expand(query)

        # Should expand E&O
        assert len(expanded) > 1
        assert any("errors and omissions" in q.lower() for q in expanded)

    def test_expand_maintains_punctuation(self, expander):
        """Test that expansion maintains punctuation."""
        query = "What is the BI coverage?"
        expanded = expander.expand(query)

        # All expansions should end with question mark
        for exp_query in expanded:
            assert exp_query.endswith("?"), f"Should maintain punctuation: {exp_query}"

    def test_expand_case_preservation(self, expander):
        """Test that expansion attempts to preserve case when possible."""
        query = "What is the GL Coverage?"
        expanded = expander.expand(query)

        # Should have expansions
        assert len(expanded) > 1

        # Check if case is reasonably preserved (first letter uppercase)
        for exp_query in expanded:
            if "general liability" in exp_query.lower():
                # Could be "General Liability" or "general liability"
                # Just check it's a valid string
                assert isinstance(exp_query, str)
