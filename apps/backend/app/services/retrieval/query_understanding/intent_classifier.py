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
        Classify query intent using rule-based pattern matching.

        Args:
            query: User's natural language query

        Returns:
            Tuple of (intent_type, confidence, traversal_depth)
            - intent_type: "QA", "ANALYSIS", or "AUDIT"
            - confidence: Float between 0.0 and 1.0
            - traversal_depth: Recommended graph traversal depth
        """
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

        # Normalize scores
        total_score = qa_score + analysis_score + audit_score

        if total_score == 0:
            # No pattern match - default to QA with low confidence
            LOGGER.info(
                "No intent pattern matched, defaulting to QA",
                extra={"query": query[:100]},
            )
            return "QA", 0.5, 1

        # Calculate confidence scores
        qa_confidence = qa_score / total_score
        analysis_confidence = analysis_score / total_score
        audit_confidence = audit_score / total_score

        # Determine intent (highest confidence)
        if audit_confidence > analysis_confidence and audit_confidence > qa_confidence:
            intent = "AUDIT"
            confidence = audit_confidence
        elif analysis_confidence > qa_confidence:
            intent = "ANALYSIS"
            confidence = analysis_confidence
        else:
            intent = "QA"
            confidence = qa_confidence

        # Get traversal depth from config
        traversal_depth = TRAVERSAL_CONFIG[intent]["max_depth"]

        # Boost confidence if multiple strong signals
        if total_score >= 3:
            confidence = min(1.0, confidence + 0.2)

        # Ensure minimum confidence threshold
        if confidence < MIN_INTENT_CONFIDENCE:
            LOGGER.warning(
                "Intent confidence below threshold, defaulting to QA",
                extra={
                    "query": query[:100],
                    "intent": intent,
                    "confidence": confidence,
                    "threshold": MIN_INTENT_CONFIDENCE,
                },
            )
            return "QA", MIN_INTENT_CONFIDENCE, 1

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
