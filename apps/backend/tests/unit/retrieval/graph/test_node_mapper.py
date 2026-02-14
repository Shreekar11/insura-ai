import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.retrieval.graph.node_mapper import NodeMapperService
from app.schemas.query import VectorSearchResult, GraphNode

@pytest.fixture
def mock_neo4j_client():
    client = MagicMock()
    client.run_query = AsyncMock()
    return client

@pytest.fixture
def node_mapper(mock_neo4j_client):
    return NodeMapperService(mock_neo4j_client)

@pytest.mark.asyncio
async def test_map_nodes_success(node_mapper, mock_neo4j_client):
    # Setup
    workflow_id = uuid.uuid4()
    vector_results = [
        VectorSearchResult(
            embedding_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            entity_id="coverages_cov_0",
            content="Property coverage",
            section_type="coverages",
            similarity_score=0.9,
            final_score=0.9,
            document_name="doc.pdf"
        )
    ]
    
    mock_neo4j_client.run_query.return_value = [
        {
            "node": {
                "id": "canonical_key_1",
                "entity_id": "coverages_cov_0",
                "workflow_id": str(workflow_id),
                "entity_type": "Coverage",
                "vector_entity_ids": ["coverages_cov_0"],
            },
            "labels": ["Coverage"],
            "node_id": "123"
        }
    ]
    
    # Execute
    results = await node_mapper.map_nodes(vector_results, workflow_id)
    
    # Assert
    assert len(results) == 1
    assert results[0].entity_id == "coverages_cov_0"
    assert results[0].entity_type == "Coverage"
    mock_neo4j_client.run_query.assert_called_once()

@pytest.mark.asyncio
async def test_map_nodes_empty(node_mapper):
    results = await node_mapper.map_nodes([], uuid.uuid4())
    assert results == []

@pytest.mark.asyncio
async def test_map_nodes_no_ids(node_mapper):
    vector_results = [
        VectorSearchResult(
            embedding_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            entity_id=None,
            content="Some text",
            section_type="general",
            similarity_score=0.5,
            final_score=0.5,
            document_name="doc.pdf"
        )
    ]
    results = await node_mapper.map_nodes(vector_results, uuid.uuid4())
    assert results == []
