"""
Query Expansion for Insurance Domain

Expands user queries using insurance domain knowledge:
- Abbreviation expansion (BI → bodily injury, GL → general liability)
- Synonym generation (deductible → self-insured retention)
- Related term expansion (claim → loss → incident)
- Query variant generation for improved recall
"""

import re
from typing import Set

from app.services.retrieval.constants import (
    INSURANCE_EXPANSIONS,
    MAX_EXPANDED_QUERIES,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class QueryExpander:
    """Expands queries using insurance domain knowledge and synonyms."""

    def expand(self, query: str, max_expansions: int = MAX_EXPANDED_QUERIES) -> list[str]:
        """
        Generate expanded query variants using insurance domain knowledge.

        Args:
            query: Original user query
            max_expansions: Maximum number of expanded queries to generate

        Returns:
            List of expanded query variants (includes original)
        """
        query_lower = query.lower()
        expanded_queries = [query]  # Always include original

        # Find all insurance terms in the query that have expansions
        matched_terms = {}
        for term, expansions in INSURANCE_EXPANSIONS.items():
            # Case-insensitive whole-word match
            pattern = r"\b" + re.escape(term.lower()) + r"\b"
            if re.search(pattern, query_lower):
                matched_terms[term] = expansions

        if not matched_terms:
            LOGGER.info(
                "No expandable terms found in query",
                extra={"query": query[:100]},
            )
            return expanded_queries

        # Generate expansion variants
        # Strategy: For each matched term, create variants replacing it with its expansions
        for term, expansions in matched_terms.items():
            # Skip the original term itself and only use alternative expansions
            alternative_expansions = [
                exp for exp in expansions
                if exp.lower() != term.lower()
            ]

            for expansion in alternative_expansions[:3]:  # Limit to top 3 per term
                # Replace the term with its expansion (case-insensitive)
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                expanded = pattern.sub(expansion, query, count=1)

                if expanded not in expanded_queries:
                    expanded_queries.append(expanded)

                # Stop if we've reached max expansions
                if len(expanded_queries) >= max_expansions:
                    break

            if len(expanded_queries) >= max_expansions:
                break

        # Deduplicate while preserving order
        seen: Set[str] = set()
        unique_expanded = []
        for eq in expanded_queries:
            eq_lower = eq.lower()
            if eq_lower not in seen:
                seen.add(eq_lower)
                unique_expanded.append(eq)

        # Limit to max_expansions
        final_queries = unique_expanded[:max_expansions]

        LOGGER.info(
            "Query expanded",
            extra={
                "original_query": query[:100],
                "matched_terms": list(matched_terms.keys()),
                "expansions_generated": len(final_queries) - 1,
                "expanded_queries": [q[:100] for q in final_queries[1:]],  # Log without original
            },
        )

        return final_queries

    def expand_term(self, term: str) -> list[str]:
        """
        Get all expansions for a single term.

        Args:
            term: Insurance term or abbreviation

        Returns:
            List of expanded terms (includes original if in expansions)
        """
        term_lower = term.lower()

        # Check if term exists in expansions dict
        if term_lower in INSURANCE_EXPANSIONS:
            return INSURANCE_EXPANSIONS[term_lower]

        # Check if term is in any expansion list
        for key, expansions in INSURANCE_EXPANSIONS.items():
            if term_lower in [exp.lower() for exp in expansions]:
                return expansions

        # No expansion found
        return [term]

    def get_canonical_term(self, term: str) -> str:
        """
        Get the canonical (full) form of an abbreviated term.

        Args:
            term: Insurance term or abbreviation

        Returns:
            Canonical term (first expansion) or original if no expansion found
        """
        expansions = self.expand_term(term)

        # Return the first (canonical) expansion
        # Convention: Full terms are listed first in INSURANCE_EXPANSIONS
        for expansion in expansions:
            if len(expansion) > len(term):
                return expansion

        return expansions[0] if expansions else term
