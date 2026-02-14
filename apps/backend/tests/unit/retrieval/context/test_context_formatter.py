import pytest
from uuid import uuid4

from app.schemas.query import MergedResult, ContextPayload
from app.services.retrieval.context.context_formatter import format_context_for_llm

def create_result(id: str, type: str, content: str, citation_id: str = None) -> MergedResult:
    res = MergedResult(
        source="vector",
        content=content,
        summary=f"Summary of {content}",
        entity_type="coverage",
        entity_id=id,
        relevance_score=0.9,
        distance=0,
        document_id=uuid4(),
        document_name=f"Doc_{id}.pdf",
        page_numbers=[1],
        section_type="coverages"
    )
    if citation_id:
        res.citation_id = citation_id
    return res

def test_format_mixed_results():
    """Test formatting with both full text and summary results."""
    full_text = [create_result("1", "full", "Content 1", "[1]")]
    
    summary = [create_result("2", "summary", "Content 2", "[2]")]
    
    payload = ContextPayload(
        full_text_results=full_text,
        summary_results=summary,
        total_results=2,
        token_count=100,
        provenance_index={}
    )
    
    output = format_context_for_llm(payload)
    
    assert "## High Priority Sources (Full Text)" in output
    assert "### Source [1]: Doc_1.pdf" in output
    assert "Content 1" in output
    
    assert "## Additional Sources (Summaries)" in output
    assert "- **[2]** Doc_2.pdf: Summary of Content 2" in output

def test_format_empty():
    """Test formatting empty payload."""
    payload = ContextPayload(
        full_text_results=[],
        summary_results=[],
        total_results=0,
        token_count=0,
        provenance_index={}
    )
    
    output = format_context_for_llm(payload)
    assert output == "No relevant context found."

def test_fallback_citation_ids():
    """Test formatting when citation_id is missing from results."""
    full_text = [create_result("1", "full", "Content 1")] # No citation_id attached
    
    payload = ContextPayload(
        full_text_results=full_text,
        summary_results=[],
        total_results=1,
        token_count=100,
        provenance_index={}
    )
    
    output = format_context_for_llm(payload)
    
    # Fallback logic should start at 1
    assert "### Source [1]:" in output
