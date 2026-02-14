import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.retrieval.graph.relevance_filter import GraphRelevanceFilterService
from app.schemas.query import GraphTraversalResult, ExtractedQueryEntities

@pytest.fixture
def mock_entity_repo():
    repo = MagicMock()
    repo.get_by_key = AsyncMock()
    return repo

@pytest.fixture
def relevance_filter(mock_entity_repo):
    return GraphRelevanceFilterService(mock_entity_repo)

@pytest.mark.asyncio
async def test_filter_and_score_basic(relevance_filter):
    # Setup
    traversal_results = [
        GraphTraversalResult(
            node_id="1",
            entity_id="e1",
            entity_type="Coverage",
            labels=["Coverage"],
            properties={"id": "key1", "name": "Property"},
            distance=1,
            relationship_chain=["HAS_COVERAGE"]
        )
    ]
    extracted = ExtractedQueryEntities(coverage_types=["property"])
    
    # Execute
    results = await relevance_filter.filter_and_score(
        traversal_results, extracted, "QA", uuid.uuid4()
    )
    
    # Assert
    assert len(results) == 1
    # Base 0.9 + Match Boost 0.05 = 0.95
    assert results[0].relevance_score >= 0.9

@pytest.mark.asyncio
async def test_hydration_trigger(relevance_filter, mock_entity_repo):
    # Setup
    sparse_result = GraphTraversalResult(
        node_id="1",
        entity_id="e1",
        entity_type="Exclusion",
        labels=["Exclusion"],
        properties={"id": "key1"}, # No description
        distance=1,
        relationship_chain=["EXCLUDES"]
    )
    extracted = ExtractedQueryEntities()
    
    mock_entity = MagicMock()
    mock_entity.attributes = {"description": "Full text from PG"}
    mock_entity.source_text = "Source text"
    mock_entity_repo.get_by_key.return_value = mock_entity
    
    # Execute
    results = await relevance_filter.filter_and_score(
        [sparse_result], extracted, "QA", uuid.uuid4()
    )
    
    # Assert
    assert results[0].properties.get("description") == "Full text from PG"
    mock_entity_repo.get_by_key.assert_called_once()

@pytest.mark.asyncio
async def test_filter_empty(relevance_filter):
    results = await relevance_filter.filter_and_score(
        [], ExtractedQueryEntities(), "QA", uuid.uuid4()
    )
    assert results == []
