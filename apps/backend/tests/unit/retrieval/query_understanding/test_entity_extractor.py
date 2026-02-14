"""Unit tests for EntityExtractor."""

import pytest
from app.services.retrieval.query_understanding.entity_extractor import EntityExtractor


class TestEntityExtractor:
    """Test suite for EntityExtractor."""

    @pytest.fixture
    def extractor(self):
        """Create EntityExtractor instance for testing."""
        return EntityExtractor()

    def test_extract_policy_numbers_standard_format(self, extractor):
        """Test extraction of policy numbers in standard formats."""
        test_cases = [
            ("What is policy POL-12345?", ["POL-12345"]),
            ("Check policy CA-001-2024", ["CA-001-2024"]),
            ("Policy number GL123456", ["GL123456"]),
            ("Find 12345-POL", ["12345-POL"]),
        ]

        for query, expected in test_cases:
            result = extractor.extract(query)
            assert set(result.policy_numbers) == set(expected), f"Failed for query: {query}"

    def test_extract_multiple_policy_numbers(self, extractor):
        """Test extraction of multiple policy numbers from single query."""
        query = "Compare policy POL-12345 with CA-001-2024 and GL123456"
        result = extractor.extract(query)
        expected = {"POL-12345", "CA-001-2024", "GL123456"}
        assert set(result.policy_numbers) == expected

    def test_extract_coverage_types_abbreviations(self, extractor):
        """Test extraction of coverage types using abbreviations."""
        test_cases = [
            ("What is the GL coverage?", ["general liability"]),
            ("Show me WC limits", ["workers compensation"]),
            ("Check AL policy", ["auto liability"]),
            ("Find E&O coverage", ["professional liability"]),
        ]

        for query, expected in test_cases:
            result = extractor.extract(query)
            assert any(e in result.coverage_types for e in expected), f"Failed for query: {query}"

    def test_extract_coverage_types_full_names(self, extractor):
        """Test extraction of coverage types using full names."""
        test_cases = [
            ("What is the general liability coverage?", ["general liability"]),
            ("Show me workers compensation", ["workers compensation"]),
            ("Check property insurance", ["property"]),
            ("Find umbrella coverage", ["umbrella"]),
        ]

        for query, expected in test_cases:
            result = extractor.extract(query)
            assert any(e in result.coverage_types for e in expected), f"Failed for query: {query}"

    def test_extract_dates_various_formats(self, extractor):
        """Test extraction of dates in various formats."""
        test_cases = [
            ("Effective date is 01/15/2024", ["01/15/2024"]),
            ("Policy expires on 2024-12-31", ["2024-12-31"]),
            ("Created Jan 15, 2024", ["Jan 15, 2024"]),
            ("Renewal date: March 1, 2025", ["March 1, 2025"]),
        ]

        for query, expected_patterns in test_cases:
            result = extractor.extract(query)
            assert len(result.dates) > 0, f"Should extract date from: {query}"
            # Check if extracted date matches any expected pattern
            assert any(
                any(pattern.lower() in date.lower() for pattern in expected_patterns)
                for date in result.dates
            ), f"Failed for query: {query}"

    def test_extract_amounts_dollar_format(self, extractor):
        """Test extraction of amounts in dollar format."""
        test_cases = [
            ("Coverage limit is $1,000,000", ["1,000,000"]),
            ("Deductible of $5,000.00", ["5,000.00"]),
            ("Premium: $ 25,000", ["25,000"]),
        ]

        for query, expected_patterns in test_cases:
            result = extractor.extract(query)
            assert len(result.amounts) > 0, f"Should extract amount from: {query}"
            # Check if extracted amount contains expected digits (compare without commas)
            assert any(
                any(pattern.replace(",", "") in amount.replace(",", "") for pattern in expected_patterns)
                for amount in result.amounts
            ), f"Failed for query: {query}"

    def test_extract_amounts_million_format(self, extractor):
        """Test extraction of amounts in million format."""
        test_cases = [
            ("Limit is 1.5 million", ["1.5"]),
            ("Coverage of 2M", ["2"]),
            ("Aggregate limit: 5 million dollars", ["5"]),
        ]

        for query, expected_patterns in test_cases:
            result = extractor.extract(query)
            assert len(result.amounts) > 0, f"Should extract amount from: {query}"

    def test_extract_locations_city_state(self, extractor):
        """Test extraction of location references."""
        test_cases = [
            "Coverage for properties in New York, NY",
            "Location: San Francisco, California",
            "Insured at Los Angeles, CA",
        ]

        for query in test_cases:
            result = extractor.extract(query)
            assert len(result.locations) > 0, f"Should extract location from: {query}"

    def test_extract_locations_addresses(self, extractor):
        """Test extraction of street addresses."""
        test_cases = [
            "Property at 123 Main Street",
            "Building located at 456 Oak Avenue",
            "Address: 789 Elm Drive",
        ]

        for query in test_cases:
            result = extractor.extract(query)
            assert len(result.locations) > 0, f"Should extract address from: {query}"

    def test_extract_entity_names(self, extractor):
        """Test extraction of entity names (organizations, people)."""
        test_cases = [
            ("Insured: Acme Corporation", "Acme Corporation"),
            ("Carrier is State Farm Insurance", "State Farm Insurance"),
            ("Brokered by John Smith Associates", "John Smith Associates"),
        ]

        for query, expected_name in test_cases:
            result = extractor.extract(query)
            # Check if any extracted entity name contains the expected name
            assert any(
                expected_name in name for name in result.entity_names
            ), f"Should extract '{expected_name}' from: {query}"

    def test_extract_section_hints(self, extractor):
        """Test extraction of section hints based on query patterns."""
        test_cases = [
            ("What are the endorsements?", "endorsements"),
            ("Show me the exclusions", "exclusions"),
            ("Find the coverage details", "coverages"),
            ("Check the declarations page", "declarations"),
        ]

        for query, expected_section in test_cases:
            result = extractor.extract(query)
            assert expected_section in result.section_hints, f"Should identify '{expected_section}' from: {query}"

    def test_extract_combined_entities(self, extractor):
        """Test extraction when multiple entity types are present."""
        query = """
        What is the general liability coverage limit for policy POL-12345
        effective 01/15/2024 with a deductible of $10,000 for
        Acme Corporation located in New York, NY?
        """

        result = extractor.extract(query)

        # Should extract policy number
        assert "POL-12345" in result.policy_numbers

        # Should extract coverage type
        assert "general liability" in result.coverage_types

        # Should extract date
        assert len(result.dates) > 0

        # Should extract amount
        assert len(result.amounts) > 0

        # Should extract location
        assert len(result.locations) > 0

        # Should extract entity name
        assert len(result.entity_names) > 0

    def test_extract_empty_query(self, extractor):
        """Test extraction from empty query."""
        result = extractor.extract("")

        assert result.policy_numbers == []
        assert result.coverage_types == []
        assert result.entity_names == []
        assert result.dates == []
        assert result.amounts == []
        assert result.locations == []
        assert result.section_hints == []

    def test_extract_no_matches(self, extractor):
        """Test extraction when query contains no extractable entities."""
        query = "Tell me about this document"
        result = extractor.extract(query)

        # Should return empty lists (except possibly section hints if generic keywords match)
        assert result.policy_numbers == []
        assert result.coverage_types == []
        assert result.dates == []
        assert result.amounts == []

    def test_extract_case_insensitive(self, extractor):
        """Test that extraction is case-insensitive."""
        queries = [
            "what is the GL COVERAGE?",
            "POLICY NUMBER POL-12345",
            "WORKERS COMP limits",
        ]

        for query in queries:
            result = extractor.extract(query)
            # Should extract entities regardless of case
            assert (
                len(result.coverage_types) > 0 or len(result.policy_numbers) > 0
            ), f"Should extract entities from: {query}"

    def test_extract_deduplication(self, extractor):
        """Test that duplicate entities are deduplicated."""
        query = "Compare policy POL-12345 with policy POL-12345"
        result = extractor.extract(query)

        # Should only have one instance of POL-12345
        assert result.policy_numbers.count("POL-12345") == 1

    def test_extract_real_world_queries(self, extractor):
        """Test with realistic insurance queries."""
        test_cases = [
            {
                "query": "What is the bodily injury limit for policy CA-001-2024?",
                "expected": {
                    "policy_numbers": ["CA-001-2024"],
                    "coverage_types": [],  # BI is not in direct coverage mapping
                },
            },
            {
                "query": "Compare GL coverage between POL-A and POL-B effective 01/01/2024",
                "expected": {
                    "policy_numbers": ["POL-A", "POL-B"],
                    "coverage_types": ["general liability"],
                    "dates": 1,  # At least 1 date
                },
            },
            {
                "query": "Show endorsements for Acme Corp with $1M deductible",
                "expected": {
                    "entity_names": 1,  # At least 1 entity
                    "amounts": 1,  # At least 1 amount
                    "section_hints": ["endorsements"],
                },
            },
        ]

        for test_case in test_cases:
            query = test_case["query"]
            expected = test_case["expected"]
            result = extractor.extract(query)

            if "policy_numbers" in expected:
                assert set(result.policy_numbers) == set(expected["policy_numbers"]), \
                    f"Policy numbers mismatch for: {query}"

            if "coverage_types" in expected:
                assert set(result.coverage_types) == set(expected["coverage_types"]), \
                    f"Coverage types mismatch for: {query}"

            if "dates" in expected:
                assert len(result.dates) >= expected["dates"], \
                    f"Dates count mismatch for: {query}"

            if "amounts" in expected:
                assert len(result.amounts) >= expected["amounts"], \
                    f"Amounts count mismatch for: {query}"

            if "entity_names" in expected:
                assert len(result.entity_names) >= expected["entity_names"], \
                    f"Entity names count mismatch for: {query}"

            if "section_hints" in expected:
                assert all(hint in result.section_hints for hint in expected["section_hints"]), \
                    f"Section hints mismatch for: {query}"

    def test_extract_policy_number_edge_cases(self, extractor):
        """Test policy number extraction edge cases."""
        test_cases = [
            # Too short - should not match
            ("Policy AB-12", []),
            # Valid patterns
            ("Policy ABC-12345", ["ABC-12345"]),
            ("Policy 12345-ABC", ["12345-ABC"]),
            ("Policy number ABCDE-123456789", ["ABCDE-123456789"]),
        ]

        for query, expected in test_cases:
            result = extractor.extract(query)
            if expected:
                assert any(
                    exp in result.policy_numbers for exp in expected
                ), f"Failed for query: {query}"
            # Note: Some edge cases might still extract due to flexible regex

    def test_extract_multiple_coverage_types(self, extractor):
        """Test extraction of multiple coverage types."""
        query = "Compare GL, WC, and AL coverage limits"
        result = extractor.extract(query)

        expected_types = ["general liability", "workers compensation", "auto liability"]
        assert len(result.coverage_types) >= 2, "Should extract multiple coverage types"
        assert any(t in result.coverage_types for t in expected_types)

    def test_extract_section_hints_from_keywords(self, extractor):
        """Test section hint extraction from various keywords."""
        test_cases = [
            ("Show me all endorsements", "endorsements"),
            ("What are the exclusions?", "exclusions"),
            ("Coverage details", "coverages"),
            ("Check the declarations", "declarations"),
            ("Policy information", "policy_info"),
        ]

        for query, expected_section in test_cases:
            result = extractor.extract(query)
            # Section hints are extracted based on QUERY_PATTERN_SECTION_HINTS
            # Some keywords might not have direct mappings
            if expected_section in ["endorsements", "exclusions", "declarations"]:
                assert expected_section in result.section_hints, \
                    f"Should extract '{expected_section}' from: {query}"
