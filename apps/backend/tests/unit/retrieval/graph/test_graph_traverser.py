import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.services.retrieval.graph.graph_traverser import GraphTraverserService
from app.schemas.query import GraphNode

@pytest.fixture
def mock_neo4j_client():
    client = MagicMock()
    client.run_query = AsyncMock()
    return client

@pytest.fixture
def traverser(mock_neo4j_client):
    return GraphTraverserService(mock_neo4j_client)

@pytest.mark.asyncio
async def test_traverse_qa_intent(traverser, mock_neo4j_client):
    # Setup
    workflow_id = uuid.uuid4()
    start_nodes = [
        GraphNode(
            node_id="123",
            entity_id="coverages_cov_0",
            entity_type="Coverage",
            labels=["Coverage"],
            properties={"name": "Prop"},
            workflow_id=workflow_id
        )
    ]
    
    mock_related = MagicMock()
    mock_related.id = "456"
    mock_data = {
        "id": "rel_key_1",
        "entity_id": "endorsements_end_0",
        "entity_type": "Endorsement",
        "document_id": str(uuid.uuid4()),
        "source_section": "endorsements"
    }
    mock_related.get.side_effect = mock_data.get
    mock_related.__iter__.return_value = mock_data.keys()
    mock_related.__getitem__.side_effect = mock_data.__getitem__

    mock_neo4j_client.run_query.return_value = [
        {
            "related": mock_related,
            "labels": ["Endorsement"],
            "distance": 1,
            "relationship_chain": ["MODIFIED_BY"],
            "node_id": "456"
        }
    ]
    
    # Execute
    results = await traverser.traverse(start_nodes, "QA", workflow_id)
    
    # Assert
    assert len(results) == 1
    assert results[0].entity_type == "Endorsement"
    assert results[0].distance == 1
    
    # Verify Cypher contains 1..1 for QA
    call_args = mock_neo4j_client.run_query.call_args
    query = call_args[0][0]
    assert "*1..1" in query

@pytest.mark.asyncio
async def test_traverse_analysis_intent(traverser, mock_neo4j_client):
    # Setup
    workflow_id = uuid.uuid4()
    start_nodes = [GraphNode(node_id="1", entity_id="e1", entity_type="T", labels=["L"], properties={}, workflow_id=workflow_id)]
    mock_neo4j_client.run_query.return_value = []
    
    # Execute
    await traverser.traverse(start_nodes, "ANALYSIS", workflow_id)
    
    # Verify Cypher contains 1..2 for ANALYSIS
    call_args = mock_neo4j_client.run_query.call_args
    query = call_args[0][0]
    assert "*1..2" in query

@pytest.mark.asyncio
async def test_traverse_empty(traverser):
    results = await traverser.traverse([], "QA", uuid.uuid4())
    assert results == []
