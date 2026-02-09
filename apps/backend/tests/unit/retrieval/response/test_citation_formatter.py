import pytest
from uuid import uuid4

from app.schemas.query import GeneratedResponse, ContextPayload, ProvenanceEntry
from app.services.retrieval.response.citation_formatter import CitationFormatterService

@pytest.fixture
def formatter():
    return CitationFormatterService()

def test_format_successful_citations(formatter):
    """Test extracting valid citations and mapping to provenance."""
    doc_id = uuid4()
    provenance = {
        "[1]": ProvenanceEntry(
            document_name="Policy_A.pdf",
            document_id=doc_id,
            page_numbers=[3],
            section_type="coverages",
            relationship_path=["HAS_COVERAGE"]
        ),
        "[2]": ProvenanceEntry(
            document_name="Policy_B.pdf",
            document_id=uuid4(),
            page_numbers=[10],
            section_type="exclusions"
        )
    }
    
    generated = GeneratedResponse(
        answer="The limit is $1M [1] but flood is excluded [2].",
        provenance=provenance,
        context_used=ContextPayload(
            full_text_results=[], 
            summary_results=[], 
            total_results=2, 
            token_count=100, 
            provenance_index=provenance
        )
    )
    
    formatted = formatter.format_response(generated)
    
    assert formatted.answer == generated.answer
    assert len(formatted.sources) == 2
    
    # Check source 1
    s1 = next(s for s in formatted.sources if s.citation_id == "1")
    assert s1.document_name == "Policy_A.pdf"
    assert s1.relationship_context == "Related via: HAS_COVERAGE"
    
    # Check source 2
    s2 = next(s for s in formatted.sources if s.citation_id == "2")
    assert s2.document_name == "Policy_B.pdf"
    assert s2.relationship_context is None

def test_format_multiple_citations_per_statement(formatter):
    """Test string like [1][2] or [1], [3]."""
    provenance = {
        "[1]": ProvenanceEntry(document_name="D1", document_id=uuid4()),
        "[3]": ProvenanceEntry(document_name="D3", document_id=uuid4()),
    }
    
    generated = GeneratedResponse(
        answer="Statement supported by many [1][3]. Also [1], [3].",
        provenance=provenance,
        context_used=ContextPayload(
            full_text_results=[], 
            summary_results=[], 
            total_results=2, 
            token_count=0, 
            provenance_index=provenance
        )
    )
    
    formatted = formatter.format_response(generated)
    assert len(formatted.sources) == 2 # Only unique IDs
    assert {s.citation_id for s in formatted.sources} == {"1", "3"}

def test_missing_provenance_warning(formatter, caplog):
    """Test citation check when LLM hallucinate an ID."""
    provenance = {"[1]": ProvenanceEntry(document_name="D1", document_id=uuid4())}
    
    generated = GeneratedResponse(
        answer="I think it's true [1] and [99].",
        provenance=provenance,
        context_used=ContextPayload(full_text_results=[], summary_results=[], total_results=1, token_count=0, provenance_index=provenance)
    )
    
    formatted = formatter.format_response(generated)
    assert len(formatted.sources) == 1
    assert "LLM cited [99] but it was not in the provenance index" in caplog.text
