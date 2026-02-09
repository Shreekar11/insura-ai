import pytest
from uuid import uuid4
from typing import List

from app.schemas.query import MergedResult
from app.services.retrieval.context.hierarchical_builder import HierarchicalContextBuilder
from app.services.processed.services.chunking.token_counter import TokenCounter

# Mock TokenCounter to return predictable counts
class MockTokenCounter(TokenCounter):
    def count_tokens(self, text: str) -> int:
        return len(text.split())

@pytest.fixture
def builder():
    return HierarchicalContextBuilder(token_counter=MockTokenCounter())

def create_mock_result(id_suffix: str, content_words: int, score: float) -> MergedResult:
    content = "word " * content_words
    return MergedResult(
        source="vector",
        content=content.strip(),
        summary=f"Summary {id_suffix}",
        entity_type="coverage",
        entity_id=f"e_{id_suffix}",
        relevance_score=score,
        document_id=uuid4(),
        document_name=f"Doc {id_suffix}",
        page_numbers=[1]
    )

def test_top_n_full_text(builder):
    """Test that top N results are included as full text."""
    results = [
        create_mock_result("1", 10, 0.9),
        create_mock_result("2", 10, 0.8),
        create_mock_result("3", 10, 0.7),
    ]
    
    # Top N=2. Budget is plenty (1000 tokens). 
    # Mock count = 10 tokens per item + 50 overhead = 60.
    payload = builder.build_context(results, max_tokens=1000, top_n_full_text=2)
    
    assert len(payload.full_text_results) == 2
    assert payload.full_text_results[0].entity_id == "e_1"
    assert payload.full_text_results[1].entity_id == "e_2"
    
    assert len(payload.summary_results) == 1
    assert payload.summary_results[0].entity_id == "e_3"
    
    # Verify citation IDs
    assert getattr(payload.full_text_results[0], "citation_id") == "[1]"
    assert getattr(payload.full_text_results[1], "citation_id") == "[2]"
    assert getattr(payload.summary_results[0], "citation_id") == "[3]"

def test_token_budget_limit(builder):
    """Test that results are truncated when budget is exceeded."""
    # Each item costs 10 (content) + 50 (overhead) = 60 tokens.
    # Budget = 100. Effective budget = 95.
    # Only 1 item should fit.
    
    results = [
        create_mock_result("1", 10, 0.9),
        create_mock_result("2", 10, 0.8),
    ]
    
    payload = builder.build_context(results, max_tokens=100, top_n_full_text=5)
    
    assert len(payload.full_text_results) == 1
    assert payload.full_text_results[0].entity_id == "e_1"
    # Result 2 should be dropped entirely as it doesn't fit
    assert len(payload.summary_results) == 0

def test_downgrade_to_summary(builder):
    """Test that heavy full text items downgrade to summary if they don't fit."""
    # Item 1: 100 words (100 tokens). Overhead 50. Total 150.
    # Budget 120. (Effective ~114).
    # Summary: 2 words (2 tokens). Overhead 50. Total 52.
    # Should fit as summary.
    
    result = create_mock_result("1", 100, 0.9)
    result.summary = "Small summary"
    
    payload = builder.build_context([result], max_tokens=120, top_n_full_text=5)
    
    assert len(payload.full_text_results) == 0
    assert len(payload.summary_results) == 1
    assert payload.summary_results[0].content.strip() == ("word " * 100).strip() # Original content preserved?
    # Wait, builder replaces .content with .summary? 
    # No, builder adds to `summary_results`. The result object itself is the same.
    # But `context_formatter` uses `result.summary` for summary results.
    # The payload groups are what matters.
    
    assert payload.summary_results[0].entity_id == "e_1"
    # Verify citation ID
    assert getattr(payload.summary_results[0], "citation_id") == "[1]"

def test_provenance_index(builder):
    """Test that provenance index is correctly built."""
    result = create_mock_result("1", 10, 0.9)
    payload = builder.build_context([result], max_tokens=1000)
    
    assert "[1]" in payload.provenance_index
    entry = payload.provenance_index["[1]"]
    assert entry.document_id == result.document_id
    assert entry.document_name == "Doc 1"
