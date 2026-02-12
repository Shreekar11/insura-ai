import pytest
from uuid import uuid4
from typing import Dict, Any

from app.schemas.query import GraphTraversalResult
from app.services.retrieval.context.result_merger import ResultMergerService


@pytest.fixture
def merger_service():
    return ResultMergerService()


@pytest.fixture
def mock_vector_result():
    doc_id = str(uuid4())
    entity_id = "coverages_cov_0"
    canonical_id = uuid4()
    return {
        "document_id": doc_id,
        "entity_id": entity_id,
        "section_type": "coverages",
        "entity_type": "coverage",
        "final_score": 0.8,
        "content": "Vector content",
        "document_name": "Policy.pdf",
        "page_numbers": [1],
        "canonical_entity_id": canonical_id,
    }


@pytest.fixture
def mock_graph_result(mock_vector_result):
    return GraphTraversalResult(
        node_id="node_1",
        entity_id=mock_vector_result["entity_id"],
        canonical_entity_id=mock_vector_result["canonical_entity_id"],
        entity_type="Coverage",
        labels=["Coverage"],
        properties={"name": "Graph Coverage", "limit": "1M"},
        distance=1,
        relationship_chain=["HAS_COVERAGE"],
        relevance_score=0.7,
        document_id=mock_vector_result["document_id"],
        source_section="coverages"
    )


@pytest.mark.asyncio
async def test_merge_disjoint_results(merger_service):
    """Test merging when vector and graph results do not overlap."""
    v_res = [{
        "document_id": str(uuid4()),
        "entity_id": "e1",
        "final_score": 0.9,
        "content": "V1"
    }]

    g_res = [GraphTraversalResult(
        node_id="n1",
        entity_id="e2",
        entity_type="Coverage",
        labels=[],
        distance=1,
        relationship_chain=[],
        relevance_score=0.8,
        document_id=uuid4(),
        source_section="coverages"
    )]

    merged = merger_service.merge(v_res, g_res)

    assert len(merged) == 2
    assert merged[0].entity_id == "e1"  # Score 0.9
    assert merged[0].source == "vector"
    assert merged[1].entity_id == "e2"  # Score 0.8
    assert merged[1].source == "graph"


@pytest.mark.asyncio
async def test_merge_overlapping_results(merger_service, mock_vector_result, mock_graph_result):
    """Test merging when vector and graph results overlap on same document+entity."""
    v_res = [mock_vector_result]
    g_res = [mock_graph_result]
    
    # Vector score 0.8, Graph score 0.7. Overlap boost +0.1. 
    # Max(0.8, 0.7) + 0.1 = 0.9.
    
    merged = merger_service.merge(v_res, g_res)
    
    assert len(merged) == 1
    result = merged[0]
    
    assert result.source == "both"
    assert result.relevance_score == pytest.approx(0.9)
    assert result.content == "Vector content"  # Prefer vector content
    assert result.distance == 1
    assert result.relationship_path == ["HAS_COVERAGE"]


@pytest.mark.asyncio
async def test_graph_only_constructs_content(merger_service):
    """Test that graph-only results generate content from properties."""
    g_res = [GraphTraversalResult(
        node_id="n1",
        entity_id="e1",
        entity_type="Exclusion",
        labels=[],
        properties={
            "name": "Flood Exclusion",
            "description": "No flood coverage",
            "random_field": "ignore_me" 
        },
        distance=0,
        relationship_chain=[],
        relevance_score=0.5,
        document_id=uuid4(),
        source_section="exclusions"
    )]
    
    merged = merger_service.merge([], g_res)
    
    assert len(merged) == 1
    content = merged[0].content
    
    assert "Entity Type: Exclusion" in content
    assert "Name: Flood Exclusion" in content
    assert "Description: No flood coverage" in content
    assert "Random field" in content  # Field names are title-cased with spaces


@pytest.mark.asyncio
async def test_skip_invalid_results(merger_service):
    """Test skipping results with missing keys."""
    v_res = [{"evidence": "Bad result"}] # Missing doc_id/entity_id
    
    g_res = [GraphTraversalResult(
        node_id="n1",
        entity_id="e1",
        entity_type="Type",
        labels=[],
        properties={},
        distance=0,
        relationship_chain=[],
        relevance_score=0.5,
        document_id=None, # Missing document_id
        source_section="s"
    )]
    
    merged = merger_service.merge(v_res, g_res)
    assert len(merged) == 0
