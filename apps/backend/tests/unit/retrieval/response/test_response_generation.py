import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.schemas.query import ContextPayload, MergedResult, ProvenanceEntry
from app.services.retrieval.response.generation_service import ResponseGenerationService

@pytest.fixture
def mock_llm_client():
    client = AsyncMock()
    client.generate_content.return_value = "The policy limit is $1,000,000 [1]."
    return client

@pytest.fixture
def service(mock_llm_client):
    with patch("app.services.retrieval.response.generation_service.create_llm_client_from_settings") as mock_factory:
        mock_factory.return_value = mock_llm_client
        svc = ResponseGenerationService()
        svc.client = mock_llm_client
        return svc

@pytest.mark.asyncio
async def test_generate_response_success(service, mock_llm_client):
    """Test successful response generation with context."""
    context = ContextPayload(
        full_text_results=[
            MergedResult(
                source="vector",
                content="Limit: $1M",
                entity_type="coverage",
                entity_id="e1",
                relevance_score=0.9,
                document_id=uuid4(),
                document_name="Doc1.pdf",
                page_numbers=[1],
                citation_id="[1]"
            )
        ],
        summary_results=[],
        total_results=1,
        token_count=100,
        provenance_index={
            "[1]": ProvenanceEntry(
                document_name="Doc1.pdf",
                document_id=uuid4()
            )
        }
    )
    
    response = await service.generate_response("What is the limit?", context)
    
    assert "limit is $1,000,000 [1]" in response.answer
    assert response.provenance == context.provenance_index
    mock_llm_client.generate_content.assert_called_once()

@pytest.mark.asyncio
async def test_generate_response_no_context(service):
    """Test response when no context is found."""
    context = ContextPayload(
        full_text_results=[],
        summary_results=[],
        total_results=0,
        token_count=0,
        provenance_index={}
    )
    
    response = await service.generate_response("Where is my data?", context)
    
    assert "couldn't find any relevant information" in response.answer
    assert response.provenance == {}

@pytest.mark.asyncio
async def test_generate_response_error_graceful_handling(service, mock_llm_client):
    """Test that errors in LLM API are handled gracefully."""
    mock_llm_client.generate_content.side_effect = Exception("API Down")
    
    context = ContextPayload(
        full_text_results=[MergedResult(source="graph", content="X", document_id=uuid4(), document_name="D", relevance_score=0.5)],
        summary_results=[],
        total_results=1,
        token_count=10,
        provenance_index={}
    )
    
    response = await service.generate_response("Query", context)
    
    assert "error occurred" in response.answer
    assert response.provenance == {}
