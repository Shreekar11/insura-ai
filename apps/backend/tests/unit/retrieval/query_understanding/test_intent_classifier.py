"""Unit tests for IntentClassifier."""

import pytest
from app.services.retrieval.query_understanding.intent_classifier import IntentClassifier


class TestIntentClassifier:
    """Test suite for IntentClassifier."""

    @pytest.fixture
    def classifier(self):
        """Create IntentClassifier instance for testing."""
        return IntentClassifier()

    def test_classify_qa_intent_simple(self, classifier):
        """Test classification of simple QA queries."""
        queries = [
            "What is the policy number?",
            "Who is the insured?",
            "When does the policy expire?",
            "How much is the premium?",
            "Show me the coverage limits",
            "List all endorsements",
        ]

        for query in queries:
            intent, confidence, depth = classifier.classify(query)
            assert intent == "QA", f"Expected QA for query: {query}"
            assert confidence > 0.0, "Confidence should be positive"
            assert depth == 1, "QA queries should have depth 1"

    def test_classify_qa_intent_detailed(self, classifier):
        """Test classification of detailed QA queries with entity mentions."""
        queries = [
            "What are the effective dates for policy POL-12345?",
            "Get the deductible amount for general liability coverage",
            "Show me the policy number and carrier information",
            "List the covered locations",
        ]

        for query in queries:
            intent, confidence, depth = classifier.classify(query)
            assert intent == "QA", f"Expected QA for query: {query}"
            assert depth == 1, "QA queries should have depth 1"

    def test_classify_analysis_intent(self, classifier):
        """Test classification of analysis queries."""
        queries = [
            "Compare the coverage limits between policies",
            "What is the difference between endorsement A and B?",
            "Analyze the impact of this exclusion",
            "Explain the relationship between coverage and deductible",
            "How do these two policies differ?",
        ]

        for query in queries:
            intent, confidence, depth = classifier.classify(query)
            assert intent == "ANALYSIS", f"Expected ANALYSIS for query: {query}"
            assert confidence > 0.0, "Confidence should be positive"
            assert depth == 2, "ANALYSIS queries should have depth 2"

    def test_classify_analysis_endorsement_focus(self, classifier):
        """Test classification of endorsement-focused analysis queries."""
        queries = [
            "How does this endorsement modify the base coverage?",
            "Explain the exclusion for cyber liability",
            "Analyze the conditions for filing a claim",
        ]

        for query in queries:
            intent, confidence, depth = classifier.classify(query)
            assert intent == "ANALYSIS", f"Expected ANALYSIS for query: {query}"
            assert depth == 2, "ANALYSIS queries should have depth 2"

    def test_classify_audit_intent(self, classifier):
        """Test classification of audit/provenance queries."""
        queries = [
            "What is the provenance of this coverage?",
            "Show me the evidence for this exclusion",
            "Trace the history of this endorsement",
            "Who created this policy modification?",
            "What is the source of this information?",
            "Show me the audit trail for these changes",
        ]

        for query in queries:
            intent, confidence, depth = classifier.classify(query)
            assert intent == "AUDIT", f"Expected AUDIT for query: {query}"
            assert confidence > 0.0, "Confidence should be positive"
            assert depth == 3, "AUDIT queries should have depth 3"

    def test_classify_mixed_patterns(self, classifier):
        """Test classification when query contains mixed patterns."""
        # QA + ANALYSIS patterns - should pick highest scoring one
        query = "What is the coverage limit and compare it with the deductible?"
        intent, confidence, depth = classifier.classify(query)
        assert intent in ["QA", "ANALYSIS"], "Should classify as either QA or ANALYSIS"

    def test_classify_no_strong_patterns(self, classifier):
        """Test classification when no strong patterns are found."""
        queries = [
            "Tell me about this insurance document",
            "I need information about the policy",
            "Can you help with this?",
        ]

        for query in queries:
            intent, confidence, depth = classifier.classify(query)
            # Should default to QA with lower confidence
            assert intent == "QA", f"Should default to QA for ambiguous query: {query}"
            assert depth == 1, "Default should be depth 1"

    def test_classify_empty_query(self, classifier):
        """Test classification of empty query."""
        query = ""
        intent, confidence, depth = classifier.classify(query)
        assert intent == "QA", "Empty query should default to QA"
        assert confidence == 0.0, "Empty query should have zero confidence"
        assert depth == 1, "Default depth should be 1"

    def test_classify_case_insensitive(self, classifier):
        """Test that classification is case-insensitive."""
        queries = [
            ("WHAT IS THE POLICY NUMBER?", "QA"),
            ("Compare THE COVERAGE LIMITS", "ANALYSIS"),
            ("SHOW ME THE EVIDENCE", "AUDIT"),
        ]

        for query, expected_intent in queries:
            intent, confidence, depth = classifier.classify(query)
            assert intent == expected_intent, f"Classification should be case-insensitive for: {query}"

    def test_traversal_depth_mapping(self, classifier):
        """Test that traversal depths are correctly mapped."""
        test_cases = [
            ("What is the coverage?", 1),  # QA → depth 1
            ("Compare coverage A and B", 2),  # ANALYSIS → depth 2
            ("Trace the provenance", 3),  # AUDIT → depth 3
        ]

        for query, expected_depth in test_cases:
            _, _, depth = classifier.classify(query)
            assert depth == expected_depth, f"Expected depth {expected_depth} for query: {query}"

    def test_confidence_scoring(self, classifier):
        """Test that confidence scores increase with more pattern matches."""
        # Query with multiple QA patterns
        query_multi = "What is the policy number, who is the insured, when does it expire, and how much is the premium?"
        _, conf_multi, _ = classifier.classify(query_multi)

        # Query with single QA pattern
        query_single = "What is the policy number?"
        _, conf_single, _ = classifier.classify(query_single)

        # Multi-pattern query should have higher confidence
        assert conf_multi > conf_single, "More pattern matches should yield higher confidence"

    def test_qa_pattern_coverage(self, classifier):
        """Test coverage of QA patterns."""
        qa_indicators = [
            "what is",
            "who is",
            "when was",
            "where is",
            "how much",
            "show me",
            "list",
            "get",
            "find",
            "display",
        ]

        for indicator in qa_indicators:
            query = f"{indicator} the coverage?"
            intent, _, _ = classifier.classify(query)
            # Should lean towards QA (though some might be ambiguous)
            assert intent in ["QA", "ANALYSIS"], f"Should classify query with '{indicator}' appropriately"

    def test_analysis_pattern_coverage(self, classifier):
        """Test coverage of ANALYSIS patterns."""
        analysis_indicators = [
            "compare",
            "difference between",
            "similar",
            "relationship",
            "impact",
            "endorsement",
            "exclusion",
            "explain",
            "analyze",
        ]

        for indicator in analysis_indicators:
            query = f"{indicator} the coverage policies"
            intent, _, _ = classifier.classify(query)
            # Should lean towards ANALYSIS
            assert intent == "ANALYSIS", f"Should classify query with '{indicator}' as ANALYSIS"

    def test_audit_pattern_coverage(self, classifier):
        """Test coverage of AUDIT patterns."""
        audit_indicators = [
            "provenance",
            "evidence",
            "source",
            "trace",
            "history",
            "audit trail",
            "version",
        ]

        for indicator in audit_indicators:
            query = f"show me the {indicator}"
            intent, _, _ = classifier.classify(query)
            # Should classify as AUDIT
            assert intent == "AUDIT", f"Should classify query with '{indicator}' as AUDIT"

    def test_real_world_insurance_queries(self, classifier):
        """Test with realistic insurance industry queries."""
        test_cases = [
            # QA queries
            ("What is the bodily injury limit for this policy?", "QA", 1),
            ("Get me the deductible amount for property damage", "QA", 1),
            ("Show me the effective date and expiration date", "QA", 1),

            # ANALYSIS queries
            ("Compare the BI limits between policy A and policy B", "ANALYSIS", 2),
            ("How does endorsement 123 modify the base GL coverage?", "ANALYSIS", 2),
            ("Analyze the impact of the cyber exclusion on our coverage", "ANALYSIS", 2),

            # AUDIT queries
            ("Trace the history of changes to this endorsement", "AUDIT", 3),
            ("Show me the evidence supporting this coverage statement", "AUDIT", 3),
            ("What is the provenance of this exclusion clause?", "AUDIT", 3),
        ]

        for query, expected_intent, expected_depth in test_cases:
            intent, confidence, depth = classifier.classify(query)
            assert intent == expected_intent, f"Expected {expected_intent} for: {query}"
            assert depth == expected_depth, f"Expected depth {expected_depth} for: {query}"
            assert confidence > 0.0, f"Should have positive confidence for: {query}"
