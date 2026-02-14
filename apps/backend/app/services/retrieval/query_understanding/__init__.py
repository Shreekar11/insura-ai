"""
Query Understanding & Intent Classification (Stage 1)

This package handles the first stage of the GraphRAG retrieval pipeline:
- Intent classification (QA, ANALYSIS, AUDIT)
- Entity extraction (policy numbers, dates, coverage types, etc.)
- Query expansion using insurance domain knowledge
- Section/entity type filtering
- Workflow context retrieval
"""

from app.services.retrieval.query_understanding.service import (
    QueryUnderstandingService,
)

__all__ = ["QueryUnderstandingService"]
