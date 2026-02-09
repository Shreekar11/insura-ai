import pytest
import uuid
import time
from unittest.mock import AsyncMock, MagicMock
from app.services.retrieval.graph.graph_expansion import GraphExpansionService
from app.schemas.query import VectorSearchResult, QueryPlan, ExtractedQueryEntities

@pytest.fixture
def mock_node_mapper():
    service = MagicMock()
    service.map_nodes = AsyncMock()
    return service

@pytest.fixture
def mock_traverser():
    service = MagicMock()
    service.traverse = AsyncMock()
    return service

@pytest.fixture
def mock_relevance_filter():
    service = MagicMock()
    service.filter_and_score = AsyncMock()
    return service

@pytest.fixture
def expansion_service(mock_node_mapper, mock_traverser, mock_relevance_filter):
    return GraphExpansionService(
        mock_node_mapper,
        mock_traverser,
        mock_relevance_filter
    )

@pytest.mark.asyncio
async def test_expand_success(
    expansion_service, 
    mock_node_mapper, 
    mock_traverser, 
    mock_relevance_filter
):
    # Setup
    workflow_id = uuid.uuid4()
    vector_results = [MagicMock(spec=VectorSearchResult, entity_id="e1")]
    query_plan = MagicMock(spec=QueryPlan, intent="QA", extracted_entities=ExtractedQueryEntities())
    
    mock_node_mapper.map_nodes.return_value = [MagicMock()]
    mock_traverser.traverse.return_value = [MagicMock()]
    mock_relevance_filter.filter_and_score.return_value = [{"result": "final"}]
    
    # Execute
    results = await expansion_service.expand(
        vector_results, query_plan, workflow_id
    )
    
    # Assert
    assert len(results) == 1
    mock_node_mapper.map_nodes.assert_called_once()
    mock_traverser.traverse.assert_called_once()
    mock_relevance_filter.filter_and_score.assert_called_once()

@pytest.mark.asyncio
async def test_expand_empty_input(expansion_service):
    results = await expansion_service.expand([], MagicMock(), uuid.uuid4())
    assert results == []

@pytest.mark.asyncio
async def test_expand_no_mapped_nodes(expansion_service, mock_node_mapper):
    mock_node_mapper.map_nodes.return_value = []
    results = await expansion_service.expand([MagicMock()], MagicMock(), uuid.uuid4())
    assert results == []
