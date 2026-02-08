"""
Entity Extraction from User Queries

Extracts structured entities from natural language queries:
- Policy numbers (e.g., POL-12345, CA-001-2024)
- Coverage types (e.g., general liability, workers comp)
- Entity names (insureds, carriers, brokers)
- Dates (effective dates, expiration dates)
- Amounts (limits, deductibles, premiums)
- Locations (addresses, cities, states)
- Section hints (declarations, endorsements, etc.)
"""

import re
from datetime import datetime

from app.schemas.query import ExtractedQueryEntities
from app.services.retrieval.constants import (
    INSURANCE_EXPANSIONS,
    QUERY_PATTERN_SECTION_HINTS,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class EntityExtractor:
    """Extracts structured entities from user queries using regex patterns."""

    # Regex patterns for entity extraction
    POLICY_NUMBER_PATTERNS = [
        r"\b[A-Z]{2,5}[-_]?\d{3,10}\b",  # POL-12345, CA001
        r"\b\d{3,10}[-_][A-Z]{2,5}\b",  # 12345-POL
        r"\bpolicy\s+(?:number\s+)?([A-Z0-9\-_]{5,15})\b",  # policy number POL-123
    ]

    DATE_PATTERNS = [
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",  # 01/15/2024, 1-15-24
        r"\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b",  # 2024-01-15
        r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})\b",  # Jan 15, 2024
    ]

    AMOUNT_PATTERNS = [
        r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",  # $1,000,000.00
        r"\b(\d{1,3}(?:,\d{3})*)\s*(?:dollars?|USD)\b",  # 1,000,000 dollars
        r"\b(\d+(?:\.\d+)?)\s*(?:million|M)\b",  # 1.5 million
    ]

    # Coverage type keywords
    COVERAGE_KEYWORDS = {
        "general liability": ["general liability", "GL", "CGL", "commercial general liability"],
        "auto liability": ["auto liability", "AL", "automobile liability", "commercial auto"],
        "workers compensation": ["workers compensation", "workers comp", "WC"],
        "professional liability": ["professional liability", "PL", "E&O", "errors and omissions"],
        "property": ["property", "building", "BPP", "business personal property"],
        "umbrella": ["umbrella", "excess liability", "excess"],
        "cyber": ["cyber", "cyber liability", "data breach"],
        "directors and officers": ["D&O", "directors and officers", "management liability"],
    }

    # Location patterns
    LOCATION_PATTERNS = [
        r"\b(\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln))\b",
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?),\s*([A-Z]{2})\b",  # City, ST
        r"\b((?:[A-Z][a-z]+\s*)+),\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",  # City, State
    ]

    def extract(self, query: str) -> ExtractedQueryEntities:
        """
        Extract structured entities from user query.

        Args:
            query: User's natural language query

        Returns:
            ExtractedQueryEntities with all extracted entities
        """
        query_lower = query.lower()

        # Extract policy numbers
        policy_numbers = self._extract_policy_numbers(query)

        # Extract coverage types
        coverage_types = self._extract_coverage_types(query_lower)

        # Extract entity names (simplified - look for capitalized words)
        entity_names = self._extract_entity_names(query)

        # Extract dates
        dates = self._extract_dates(query)

        # Extract amounts
        amounts = self._extract_amounts(query)

        # Extract locations
        locations = self._extract_locations(query)

        # Extract section hints based on query patterns
        section_hints = self._extract_section_hints(query_lower)

        entities = ExtractedQueryEntities(
            policy_numbers=policy_numbers,
            coverage_types=coverage_types,
            entity_names=entity_names,
            dates=dates,
            amounts=amounts,
            locations=locations,
            section_hints=section_hints,
        )

        LOGGER.info(
            "Entities extracted",
            extra={
                "query": query[:100],
                "policy_numbers": len(policy_numbers),
                "coverage_types": len(coverage_types),
                "entity_names": len(entity_names),
                "dates": len(dates),
                "amounts": len(amounts),
                "locations": len(locations),
                "section_hints": len(section_hints),
            },
        )

        return entities

    def _extract_policy_numbers(self, query: str) -> list[str]:
        """Extract policy numbers using multiple regex patterns."""
        policy_numbers = []

        for pattern in self.POLICY_NUMBER_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            policy_numbers.extend(matches)

        # Deduplicate and clean
        return list(set(pol.strip() for pol in policy_numbers if pol.strip()))

    def _extract_coverage_types(self, query_lower: str) -> list[str]:
        """Extract coverage types by matching against known keywords."""
        coverage_types = []

        for coverage_name, keywords in self.COVERAGE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    coverage_types.append(coverage_name)
                    break  # Only add once per coverage type

        return coverage_types

    def _extract_entity_names(self, query: str) -> list[str]:
        """
        Extract potential entity names (organizations, people).

        Simplified approach: Look for capitalized words/phrases.
        In production, this could use NER (Named Entity Recognition).
        """
        # Pattern: 2-4 consecutive capitalized words
        pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
        matches = re.findall(pattern, query)

        # Filter out common false positives
        stopwords = {
            "What", "When", "Where", "Who", "How", "Why", "Which",
            "The", "This", "That", "These", "Those",
            "Policy", "Coverage", "Endorsement", "Exclusion",
        }

        entity_names = [
            match for match in matches
            if not any(word in match for word in stopwords)
        ]

        return list(set(entity_names))[:10]  # Limit to top 10

    def _extract_dates(self, query: str) -> list[str]:
        """Extract dates in various formats."""
        dates = []

        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            dates.extend(matches)

        # Deduplicate and clean
        return list(set(date.strip() for date in dates if date.strip()))

    def _extract_amounts(self, query: str) -> list[str]:
        """Extract monetary amounts and numeric values."""
        amounts = []

        for pattern in self.AMOUNT_PATTERNS:
            matches = re.findall(pattern, query, re.IGNORECASE)
            amounts.extend(matches)

        # Deduplicate and clean
        return list(set(amt.strip() for amt in amounts if amt.strip()))

    def _extract_locations(self, query: str) -> list[str]:
        """Extract location references (addresses, cities, states)."""
        locations = []

        for pattern in self.LOCATION_PATTERNS:
            matches = re.findall(pattern, query)
            # Flatten tuples from group matches
            if matches:
                for match in matches:
                    if isinstance(match, tuple):
                        locations.extend([m for m in match if m])
                    else:
                        locations.append(match)

        # Deduplicate and clean
        return list(set(loc.strip() for loc in locations if loc.strip()))

    def _extract_section_hints(self, query_lower: str) -> list[str]:
        """
        Extract section hints based on query pattern matching.

        Uses QUERY_PATTERN_SECTION_HINTS mapping from constants.
        """
        section_hints = []

        for keyword, sections in QUERY_PATTERN_SECTION_HINTS.items():
            if keyword in query_lower:
                section_hints.extend(sections)

        # Deduplicate
        return list(set(section_hints))
