"""Integration tests for GraphBuilder service.

Tests entity node creation, relationship edge creation, and schema compliance
with the predefined graph schema.

Run with: pytest tests/integration/test_graph_builder_integration.py -v
"""

import pytest
import uuid
from datetime import datetime, date
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.summarized.services.indexing.graph.graph_builder import GraphBuilder


# Test Data based on the provided JSON examples
DECLARATIONS_JSON = {
    "fields": {
        "policy_number": "POL-8888",
        "effective_date": "2024-01-01",
        "expiration_date": "2025-01-01",
        "total_premium": 5000.00
    },
    "entities": [
        {
            "type": "Policy",
            "id": "policy_POL-8888",
            "confidence": 0.99,
            "attributes": {
                "policy_number": "POL-8888",
                "policy_type": "Commercial General Liability",
                "effective_date": "2024-01-01",
                "expiration_date": "2025-01-01",
                "total_premium": 5000.00,
                "base_premium": 4500.00,
                "status": "active"
            }
        },
        {
            "type": "Organization",
            "id": "org_acme_insurance",
            "confidence": 0.98,
            "attributes": {
                "name": "Acme Insurance Co",
                "role": "carrier",
                "address": "100 Insurance Plaza, New York, NY"
            }
        },
        {
            "type": "Organization",
            "id": "org_tech_solutions",
            "confidence": 0.98,
            "attributes": {
                "name": "Tech Solutions Inc",
                "role": "insured",
                "address": "456 Tech Avenue, Austin, TX"
            }
        },
        {
            "type": "Location",
            "id": "loc_123_innovation_dr",
            "confidence": 0.95,
            "attributes": {
                "location_id": "LOC-001",
                "address": "123 Innovation Dr, San Francisco, CA",
                "construction_type": "Frame",
                "occupancy": "Office",
                "building_value": 2000000.00,
                "tiv": 2500000.00
            }
        }
    ],
    "confidence": 0.99
}

COVERAGES_JSON = {
    "coverages": [
        {
            "name": "General Liability",
            "limit": 1000000,
            "deductible": 5000
        }
    ],
    "entities": [
        {
            "type": "Coverage",
            "id": "cov_general_liability",
            "confidence": 0.97,
            "attributes": {
                "name": "General Liability",
                "coverage_type": "Liability",
                "per_occurrence_limit": 1000000.00,
                "aggregate_limit": 2000000.00,
                "deductible_amount": 5000.00,
                "included": True
            }
        }
    ],
    "confidence": 0.97
}

ENDORSEMENTS_JSON = {
    "endorsements": [
        {
            "number": "CG 20 10",
            "name": "Additional Insured"
        }
    ],
    "entities": [
        {
            "type": "Endorsement",
            "id": "end_cg_20_10",
            "confidence": 0.96,
            "attributes": {
                "form_number": "CG 20 10",
                "endorsement_number": "CG 20 10",
                "name": "Additional Insured - Owners, Lessees or Contractors",
                "effective_date": "2024-01-01",
                "description": "Provides additional insured coverage"
            }
        }
    ],
    "confidence": 0.96
}


class MockEntity:
    """Mock Entity model for testing."""
    
    def __init__(self, entity_data: Dict[str, Any], entity_id: uuid.UUID = None):
        self.id = entity_id or uuid.uuid4()
        self.entity_type = entity_data["type"]
        self.canonical_key = entity_data["id"]
        self.attributes = entity_data["attributes"]
        self.created_at = datetime.utcnow()
        self.confidence = entity_data.get("confidence", 0.95)


class MockEntityRelationship:
    """Mock EntityRelationship model for testing."""
    
    def __init__(
        self, 
        rel_id: uuid.UUID,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        relationship_type: str,
        confidence: float = 0.9,
        attributes: Dict = None
    ):
        self.id = rel_id
        self.source_entity_id = source_entity_id
        self.target_entity_id = target_entity_id
        self.relationship_type = relationship_type
        self.confidence = confidence
        self.attributes = attributes or {}
        self.created_at = datetime.utcnow()


class MockVectorEmbedding:
    """Mock VectorEmbedding model for testing."""
    
    def __init__(self, entity_id: uuid.UUID, section_type: str = "full_text"):
        self.id = uuid.uuid4()
        self.entity_id = entity_id
        self.section_type = section_type
        self.embedding_dim = 384
        self.created_at = datetime.utcnow()


@pytest.fixture
def workflow_id():
    """Fixture for workflow ID."""
    return uuid.uuid4()


@pytest.fixture
def document_id():
    """Fixture for document ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_neo4j_driver():
    """Fixture for mocked Neo4j driver."""
    driver = AsyncMock()
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def mock_db_session():
    """Fixture for mocked database session."""
    return AsyncMock()


@pytest.fixture
def mock_entities(workflow_id):
    """Fixture for mock entities from all JSON examples."""
    entities = []
    
    # Create entities from declarations
    for entity_data in DECLARATIONS_JSON["entities"]:
        entities.append(MockEntity(entity_data))
    
    # Add coverage entity
    for entity_data in COVERAGES_JSON["entities"]:
        entities.append(MockEntity(entity_data))
    
    # Add endorsement entity
    for entity_data in ENDORSEMENTS_JSON["entities"]:
        entities.append(MockEntity(entity_data))
    
    return entities


@pytest.fixture
def mock_relationships(mock_entities):
    """Fixture for mock relationships between entities."""
    # Map canonical keys to entities for easy lookup
    entity_map = {e.canonical_key: e for e in mock_entities}
    
    relationships = []
    
    # Policy -> Organization (ISSUED_BY)
    if "policy_POL-8888" in entity_map and "org_acme_insurance" in entity_map:
        relationships.append(MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=entity_map["policy_POL-8888"].id,
            target_entity_id=entity_map["org_acme_insurance"].id,
            relationship_type="ISSUED_BY",
            confidence=0.99,
            attributes={"evidence": ["Policy issued by Acme Insurance Co"]}
        ))
    
    # Policy -> Organization (HAS_INSURED)
    if "policy_POL-8888" in entity_map and "org_tech_solutions" in entity_map:
        relationships.append(MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=entity_map["policy_POL-8888"].id,
            target_entity_id=entity_map["org_tech_solutions"].id,
            relationship_type="HAS_INSURED",
            confidence=0.98,
            attributes={"evidence": ["Named insured: Tech Solutions Inc"]}
        ))
    
    # Policy -> Location (HAS_LOCATION)
    if "policy_POL-8888" in entity_map and "loc_123_innovation_dr" in entity_map:
        relationships.append(MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=entity_map["policy_POL-8888"].id,
            target_entity_id=entity_map["loc_123_innovation_dr"].id,
            relationship_type="HAS_LOCATION",
            confidence=0.95,
            attributes={"evidence": ["Location: 123 Innovation Dr"]}
        ))
    
    # Policy -> Coverage (HAS_COVERAGE)
    if "policy_POL-8888" in entity_map and "cov_general_liability" in entity_map:
        relationships.append(MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=entity_map["policy_POL-8888"].id,
            target_entity_id=entity_map["cov_general_liability"].id,
            relationship_type="HAS_COVERAGE",
            confidence=0.97,
            attributes={"evidence": ["Coverage includes General Liability"]}
        ))
    
    # Coverage -> Endorsement (MODIFIED_BY)
    if "cov_general_liability" in entity_map and "end_cg_20_10" in entity_map:
        relationships.append(MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=entity_map["cov_general_liability"].id,
            target_entity_id=entity_map["end_cg_20_10"].id,
            relationship_type="MODIFIED_BY",
            confidence=0.96,
            attributes={"evidence": ["Endorsement CG 20 10 modifies coverage"]}
        ))
    
    return relationships


@pytest.fixture
async def graph_builder(mock_neo4j_driver, mock_db_session):
    """Fixture for GraphBuilder instance."""
    builder = GraphBuilder(mock_neo4j_driver, mock_db_session)
    
    # Mock the neo4j_session attribute that's used in _create_entity_node
    builder.neo4j_session = AsyncMock()
    builder.neo4j_session.run = AsyncMock()
    
    return builder


@pytest.mark.asyncio
class TestGraphBuilderIntegration:
    """Integration tests for GraphBuilder service."""
    
    async def test_run_creates_all_entities_and_relationships(
        self,
        graph_builder,
        workflow_id,
        mock_entities,
        mock_relationships
    ):
        """Test that run() creates all entities and relationships."""
        # Mock repository methods
        graph_builder.entity_repo.get_by_workflow = AsyncMock(return_value=mock_entities)
        graph_builder.rel_repo.get_by_workflow = AsyncMock(return_value=mock_relationships)
        graph_builder.emb_repo.get_by_document = AsyncMock(return_value=[])
        
        # Mock entity lookups for relationships
        entity_map = {e.id: e for e in mock_entities}
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: entity_map.get(eid)
        )
        
        # Run the graph builder
        stats = await graph_builder.run(str(workflow_id))
        
        # Verify statistics
        assert stats["entities_created"] == len(mock_entities)
        assert stats["relationships_created"] == len(mock_relationships)
        assert stats["errors"] == 0
        
        # Verify entity creation was called for each entity
        assert graph_builder.neo4j_session.run.call_count >= len(mock_entities)
    
    async def test_create_policy_node_with_schema_compliance(
        self,
        graph_builder,
        workflow_id
    ):
        """Test Policy node creation matches schema definition."""
        policy_entity = MockEntity(DECLARATIONS_JSON["entities"][0])
        
        await graph_builder._create_entity_node(policy_entity, workflow_id)
        
        # Verify the Cypher query was called
        call_args = graph_builder.neo4j_session.run.call_args
        cypher_query = call_args[0][0]
        properties = call_args[0][1]
        
        # Verify node label
        assert "Policy" in cypher_query
        
        # Verify required schema fields from PolicyNode
        assert properties["id"] == "policy_POL-8888"
        assert properties["policy_number"] == "POL-8888"
        assert properties["policy_type"] == "Commercial General Liability"
        assert properties["effective_date"] == "2024-01-01"
        assert properties["expiration_date"] == "2025-01-01"
        assert properties["total_premium"] == 5000.00
        assert properties["base_premium"] == 4500.00
        assert properties["status"] == "active"
        assert properties["workflow_id"] == str(workflow_id)
    
    async def test_create_organization_node_with_schema_compliance(
        self,
        graph_builder,
        workflow_id
    ):
        """Test Organization node creation matches schema definition."""
        org_entity = MockEntity(DECLARATIONS_JSON["entities"][1])
        
        await graph_builder._create_entity_node(org_entity, workflow_id)
        
        call_args = graph_builder.neo4j_session.run.call_args
        cypher_query = call_args[0][0]
        properties = call_args[0][1]
        
        # Verify node label
        assert "Organization" in cypher_query
        
        # Verify required schema fields from OrganizationNode
        assert properties["id"] == "org_acme_insurance"
        assert properties["name"] == "Acme Insurance Co"
        assert properties["role"] == "carrier"  # Must match OrganizationRole enum
        assert properties["address"] == "100 Insurance Plaza, New York, NY"
        assert properties["workflow_id"] == str(workflow_id)
    
    async def test_create_location_node_with_schema_compliance(
        self,
        graph_builder,
        workflow_id
    ):
        """Test Location node creation matches schema definition."""
        location_entity = MockEntity(DECLARATIONS_JSON["entities"][3])
        
        await graph_builder._create_entity_node(location_entity, workflow_id)
        
        call_args = graph_builder.neo4j_session.run.call_args
        cypher_query = call_args[0][0]
        properties = call_args[0][1]
        
        # Verify node label
        assert "Location" in cypher_query
        
        # Verify required schema fields from LocationNode
        assert properties["id"] == "loc_123_innovation_dr"
        assert properties["location_id"] == "LOC-001"
        assert properties["address"] == "123 Innovation Dr, San Francisco, CA"
        assert properties["construction_type"] == "Frame"
        assert properties["occupancy"] == "Office"
        assert properties["building_value"] == 2000000.00
        assert properties["tiv"] == 2500000.00
        assert properties["workflow_id"] == str(workflow_id)
    
    async def test_create_coverage_node_with_schema_compliance(
        self,
        graph_builder,
        workflow_id
    ):
        """Test Coverage node creation matches schema definition."""
        coverage_entity = MockEntity(COVERAGES_JSON["entities"][0])
        
        await graph_builder._create_entity_node(coverage_entity, workflow_id)
        
        call_args = graph_builder.neo4j_session.run.call_args
        cypher_query = call_args[0][0]
        properties = call_args[0][1]
        
        # Verify node label
        assert "Coverage" in cypher_query
        
        # Verify required schema fields from CoverageNode
        assert properties["id"] == "cov_general_liability"
        assert properties["name"] == "General Liability"
        assert properties["coverage_type"] == "Liability"
        assert properties["per_occurrence_limit"] == 1000000.00
        assert properties["aggregate_limit"] == 2000000.00
        assert properties["deductible_amount"] == 5000.00
        assert properties["included"] is True
        assert properties["workflow_id"] == str(workflow_id)
    
    async def test_create_endorsement_node_with_schema_compliance(
        self,
        graph_builder,
        workflow_id
    ):
        """Test Endorsement node creation matches schema definition."""
        endorsement_entity = MockEntity(ENDORSEMENTS_JSON["entities"][0])
        
        await graph_builder._create_entity_node(endorsement_entity, workflow_id)
        
        call_args = graph_builder.neo4j_session.run.call_args
        cypher_query = call_args[0][0]
        properties = call_args[0][1]
        
        # Verify node label
        assert "Endorsement" in cypher_query
        
        # Verify required schema fields from EndorsementNode
        assert properties["id"] == "end_cg_20_10"
        assert properties["endorsement_number"] == "CG 20 10"
        assert properties["name"] == "Additional Insured - Owners, Lessees or Contractors"
        assert properties["effective_date"] == "2024-01-01"
        assert properties["description"] == "Provides additional insured coverage"
        assert properties["workflow_id"] == str(workflow_id)
    
    async def test_create_relationship_issued_by(
        self,
        graph_builder,
        workflow_id,
        mock_entities
    ):
        """Test ISSUED_BY relationship creation."""
        entity_map = {e.canonical_key: e for e in mock_entities}
        policy = entity_map["policy_POL-8888"]
        carrier = entity_map["org_acme_insurance"]
        
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=policy.id,
            target_entity_id=carrier.id,
            relationship_type="ISSUED_BY",
            confidence=0.99
        )
        
        # Mock entity lookups
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: policy if eid == policy.id else carrier
        )
        
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        # Verify the Cypher query
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        cypher_query = call_args[0][0]
        params = call_args[0][1]
        
        # Verify relationship type matches RelationshipType enum
        assert "ISSUED_BY" in cypher_query
        assert params["source_key"] == "policy_POL-8888"
        assert params["target_key"] == "org_acme_insurance"
        assert params["confidence"] == 0.99
        assert params["workflow_id"] == str(workflow_id)
    
    async def test_create_relationship_has_insured(
        self,
        graph_builder,
        workflow_id,
        mock_entities
    ):
        """Test HAS_INSURED relationship creation."""
        entity_map = {e.canonical_key: e for e in mock_entities}
        policy = entity_map["policy_POL-8888"]
        insured = entity_map["org_tech_solutions"]
        
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=policy.id,
            target_entity_id=insured.id,
            relationship_type="HAS_INSURED",
            confidence=0.98
        )
        
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: policy if eid == policy.id else insured
        )
        
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        cypher_query = call_args[0][0]
        params = call_args[0][1]
        
        # Verify relationship type matches RelationshipType enum
        assert "HAS_INSURED" in cypher_query
        assert params["source_key"] == "policy_POL-8888"
        assert params["target_key"] == "org_tech_solutions"
    
    async def test_create_relationship_has_coverage(
        self,
        graph_builder,
        workflow_id,
        mock_entities
    ):
        """Test HAS_COVERAGE relationship creation."""
        entity_map = {e.canonical_key: e for e in mock_entities}
        policy = entity_map["policy_POL-8888"]
        coverage = entity_map["cov_general_liability"]
        
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=policy.id,
            target_entity_id=coverage.id,
            relationship_type="HAS_COVERAGE",
            confidence=0.97
        )
        
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: policy if eid == policy.id else coverage
        )
        
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        cypher_query = call_args[0][0]
        params = call_args[0][1]
        
        # Verify relationship type matches RelationshipType enum
        assert "HAS_COVERAGE" in cypher_query
        assert params["source_key"] == "policy_POL-8888"
        assert params["target_key"] == "cov_general_liability"
    
    async def test_create_relationship_modified_by(
        self,
        graph_builder,
        workflow_id,
        mock_entities
    ):
        """Test MODIFIED_BY relationship creation."""
        entity_map = {e.canonical_key: e for e in mock_entities}
        coverage = entity_map["cov_general_liability"]
        endorsement = entity_map["end_cg_20_10"]
        
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=coverage.id,
            target_entity_id=endorsement.id,
            relationship_type="MODIFIED_BY",
            confidence=0.96
        )
        
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: coverage if eid == coverage.id else endorsement
        )
        
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        cypher_query = call_args[0][0]
        params = call_args[0][1]
        
        # Verify relationship type matches RelationshipType enum
        assert "MODIFIED_BY" in cypher_query
        assert params["source_key"] == "cov_general_liability"
        assert params["target_key"] == "end_cg_20_10"
    
    async def test_create_relationship_has_location(
        self,
        graph_builder,
        workflow_id,
        mock_entities
    ):
        """Test HAS_LOCATION relationship creation."""
        entity_map = {e.canonical_key: e for e in mock_entities}
        policy = entity_map["policy_POL-8888"]
        location = entity_map["loc_123_innovation_dr"]
        
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=policy.id,
            target_entity_id=location.id,
            relationship_type="HAS_LOCATION",
            confidence=0.95
        )
        
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: policy if eid == policy.id else location
        )
        
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        cypher_query = call_args[0][0]
        params = call_args[0][1]
        
        # Verify relationship type matches RelationshipType enum
        assert "HAS_LOCATION" in cypher_query
        assert params["source_key"] == "policy_POL-8888"
        assert params["target_key"] == "loc_123_innovation_dr"
    
    async def test_relationship_evidence_attributes(
        self,
        graph_builder,
        workflow_id,
        mock_entities
    ):
        """Test that relationship evidence is properly stored."""
        entity_map = {e.canonical_key: e for e in mock_entities}
        policy = entity_map["policy_POL-8888"]
        carrier = entity_map["org_acme_insurance"]
        
        evidence = ["Policy issued by Acme Insurance Co", "Document reference: Page 1"]
        
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=policy.id,
            target_entity_id=carrier.id,
            relationship_type="ISSUED_BY",
            confidence=0.99,
            attributes={"evidence": evidence}
        )
        
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: policy if eid == policy.id else carrier
        )
        
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        params = call_args[0][1]
        
        # Verify evidence is stored
        assert params["evidence"] == evidence
        assert params["source"] == "llm_extraction"
    
    async def test_create_embedding_node(
        self,
        graph_builder,
        workflow_id
    ):
        """Test vector embedding node creation."""
        entity_id = uuid.uuid4()
        embedding = MockVectorEmbedding(entity_id, "full_text")
        
        await graph_builder._create_embedding_node(embedding, str(workflow_id))
        
        call_args = graph_builder.neo4j_driver.execute_query.call_args
        cypher_query = call_args[0][0]
        params = call_args[0][1]
        
        # Verify node creation
        assert "VectorEmbedding" in cypher_query
        assert params["entity_id"] == str(entity_id)
        assert params["section_type"] == "full_text"
        assert params["embedding_dim"] == 384
        assert params["confidence"] == 0.95
        assert params["workflow_id"] == str(workflow_id)
    
    async def test_map_entity_properties_removes_none_values(
        self,
        graph_builder
    ):
        """Test that None values are filtered out from properties."""
        entity_data = {
            "type": "Policy",
            "id": "policy_test",
            "attributes": {
                "policy_number": "POL-123",
                "policy_type": None,  # Should be removed
                "effective_date": "2024-01-01",
                "expiration_date": None  # Should be removed
            }
        }
        entity = MockEntity(entity_data)
        
        properties = graph_builder._map_entity_properties(entity)
        
        # Verify None values are not in properties
        assert "policy_number" in properties
        assert "effective_date" in properties
        assert "policy_type" not in properties
        assert "expiration_date" not in properties
    
    async def test_run_with_document_scope(
        self,
        graph_builder,
        workflow_id,
        document_id,
        mock_entities,
        mock_relationships
    ):
        """Test run() with document-scoped fetching."""
        # Mock repository methods for document scope
        graph_builder.entity_repo.get_by_document = AsyncMock(return_value=mock_entities[:2])
        graph_builder.rel_repo.get_by_document = AsyncMock(return_value=mock_relationships[:1])
        graph_builder.emb_repo.get_by_document = AsyncMock(return_value=[])
        
        # Mock entity lookups
        entity_map = {e.id: e for e in mock_entities}
        graph_builder.entity_repo.get_by_id = AsyncMock(
            side_effect=lambda eid: entity_map.get(eid)
        )
        
        stats = await graph_builder.run(str(workflow_id), str(document_id))
        
        # Verify only document-scoped entities were processed
        assert stats["entities_created"] == 2
        assert stats["relationships_created"] == 1
        assert stats["errors"] == 0
        
        # Verify correct repository methods were called
        graph_builder.entity_repo.get_by_document.assert_called_once()
        graph_builder.rel_repo.get_by_document.assert_called_once()
    
    async def test_error_handling_for_missing_entities(
        self,
        graph_builder,
        workflow_id
    ):
        """Test error handling when source or target entity is missing."""
        relationship = MockEntityRelationship(
            rel_id=uuid.uuid4(),
            source_entity_id=uuid.uuid4(),  # Non-existent
            target_entity_id=uuid.uuid4(),  # Non-existent
            relationship_type="HAS_COVERAGE"
        )
        
        # Mock entity lookup to return None
        graph_builder.entity_repo.get_by_id = AsyncMock(return_value=None)
        
        # Should not raise, but should log warning and return early
        await graph_builder._create_relationship_edge(relationship, str(workflow_id))
        
        # Verify execute_query was NOT called
        graph_builder.neo4j_driver.execute_query.assert_not_called()
    
