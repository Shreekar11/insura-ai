"""
Intent Classification for GraphRAG Queries

Classifies user queries into one of three intent types:
- QA: Simple factual questions (1-hop traversal)
- ANALYSIS: Comparative/analytical queries (2-hop traversal)
- AUDIT: Provenance/evidence chains (3+ hop traversal)
"""

import re
from typing import Literal

from app.services.retrieval.constants import (
    MIN_INTENT_CONFIDENCE,
    TRAVERSAL_CONFIG,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

IntentType = Literal["QA", "ANALYSIS", "AUDIT"]


class IntentClassifier:
    """Classifies user query intent using rule-based patterns."""

    # Rule-based patterns for intent classification
    QA_PATTERNS = [
        r"\bwhat\s+is\b",
        r"\bwho\s+is\b",
        r"\bwhen\s+(was|is|does)\b",
        r"\bwhere\s+is\b",
        r"\bhow\s+much\b",
        r"\bshow\s+me\b",
        r"\blist\b",
        r"\bget\b",
        r"\bfind\b",
        r"\btell\s+me\b",
        r"\bpolicy\s+number\b",
        r"\beffective\s+date\b",
        r"\bexpiration\s+date\b",
        r"\bcarrier\b",
        r"\binsured\b",
        r"\bpremium\b",
        r"\blimit\b",
        r"\bdeductible\b",
    ]

    ANALYSIS_PATTERNS = [
        r"\bcompare\b",
        r"\bdifference\s+between\b",
        r"\bsimilar\b",
        r"\brelationship\b",
        r"\bconnect(ed|ion)?\b",
        r"\bimpact\b",
        r"\baffect\b",
        r"\bmodified\s+by\b",
        r"\bendorsement\b",
        r"\bexclusion\b",
        r"\bsubject\s+to\b",
        r"\bcondition\b",
        r"\bhow\s+do(es)?\b",
        r"\bwhy\b",
        r"\bexplain\b",
        r"\banalyze\b",
        r"\bsummarize\b",
        r"\boverview\b",
    ]

    AUDIT_PATTERNS = [
        r"\bprovenance\b",
        r"\bevidence\b",
        r"\bsource\b",
        r"\btrace\b",
        r"\bhistory\b",
        r"\borigin\b",
        r"\bchain\b",
        r"\bwhere\s+(did|does)\s+.+\s+come\s+from\b",
        r"\bwho\s+(created|modified|added)\b",
        r"\bwhen\s+(was\s+.+\s+(created|modified|added))\b",
        r"\bchanges\b",
        r"\bmodification\b",
        r"\baudit\s+trail\b",
        r"\bversion\b",
        r"\bshow\s+.+\s+changes\b",
    ]

    def classify(self, query: str) -> tuple[IntentType, float, int]:
        """
        Classify query intent using rule-based pattern matching with weighted scoring.

        Args:
            query: User's natural language query

        Returns:
            Tuple of (intent_type, confidence, traversal_depth)
            - intent_type: "QA", "ANALYSIS", or "AUDIT"
            - confidence: Float between 0.0 and 1.0
            - traversal_depth: Recommended graph traversal depth
        """
        # Handle empty query
        if not query or not query.strip():
            LOGGER.info("Empty query, returning default QA intent with zero confidence")
            return "QA", 0.0, 1

        query_lower = query.lower()

        # Count pattern matches for each intent type
        qa_score = sum(
            1 for pattern in self.QA_PATTERNS if re.search(pattern, query_lower)
        )
        analysis_score = sum(
            1
            for pattern in self.ANALYSIS_PATTERNS
            if re.search(pattern, query_lower)
        )
        audit_score = sum(
            1 for pattern in self.AUDIT_PATTERNS if re.search(pattern, query_lower)
        )

        # Apply pattern weighting - AUDIT patterns have highest priority
        # This ensures provenance/evidence queries are classified correctly
        AUDIT_WEIGHT = 2.0
        ANALYSIS_WEIGHT = 1.5
        QA_WEIGHT = 1.0

        weighted_qa = qa_score * QA_WEIGHT
        weighted_analysis = analysis_score * ANALYSIS_WEIGHT
        weighted_audit = audit_score * AUDIT_WEIGHT

        # Normalize scores
        total_weighted_score = weighted_qa + weighted_analysis + weighted_audit

        if total_weighted_score == 0:
            # No pattern match - default to QA with low confidence
            LOGGER.info(
                "No intent pattern matched, defaulting to QA",
                extra={"query": query[:100]},
            )
            return "QA", 0.5, 1

        # Calculate confidence scores based on weighted scores
        qa_confidence = weighted_qa / total_weighted_score
        analysis_confidence = weighted_analysis / total_weighted_score
        audit_confidence = weighted_audit / total_weighted_score

        # Determine intent (highest weighted confidence)
        if audit_confidence > analysis_confidence and audit_confidence > qa_confidence:
            intent = "AUDIT"
            confidence = audit_confidence
            raw_score = audit_score
        elif analysis_confidence > qa_confidence:
            intent = "ANALYSIS"
            confidence = analysis_confidence
            raw_score = analysis_score
        else:
            intent = "QA"
            confidence = qa_confidence
            raw_score = qa_score

        # Get traversal depth from config
        traversal_depth = TRAVERSAL_CONFIG[intent]["max_depth"]

        # Cap base confidence to leave room for boost to differentiate multi-pattern queries
        # Only apply cap when there are multiple patterns to allow for differentiation
        total_patterns = qa_score + analysis_score + audit_score
        if total_patterns >= 2:
            confidence = min(0.85, confidence)

        # Boost confidence if multiple strong signals (but don't exceed 1.0)
        # Scale boost based on number of patterns to differentiate multi-pattern queries
        if raw_score >= 2:
            boost = min(0.2, (raw_score - 1) * 0.05)  # 0.05 per additional pattern, max 0.2
            confidence = min(1.0, confidence + boost)

        # Only apply minimum confidence threshold for QA intent
        # For AUDIT and ANALYSIS, trust the weighted scoring if they have explicit matches
        if intent == "QA" and confidence < MIN_INTENT_CONFIDENCE:
            LOGGER.warning(
                "QA intent confidence below threshold, defaulting to QA with minimum confidence",
                extra={
                    "query": query[:100],
                    "confidence": confidence,
                    "threshold": MIN_INTENT_CONFIDENCE,
                },
            )
            return "QA", MIN_INTENT_CONFIDENCE, 1

        # For AUDIT/ANALYSIS with low confidence, only fall back if confidence is very low
        # This handles cases where patterns are diluted across multiple intent types
        if intent in ["AUDIT", "ANALYSIS"] and confidence < 0.35:
            LOGGER.warning(
                f"{intent} confidence too low ({confidence:.2f}), falling back to QA",
                extra={
                    "query": query[:100],
                    "intent": intent,
                    "confidence": confidence,
                },
            )
            return "QA", 0.5, 1

        LOGGER.info(
            "Intent classified",
            extra={
                "query": query[:100],
                "intent": intent,
                "confidence": confidence,
                "traversal_depth": traversal_depth,
                "scores": {
                    "qa": qa_score,
                    "analysis": analysis_score,
                    "audit": audit_score,
                },
            },
        )

        return intent, confidence, traversal_depth
