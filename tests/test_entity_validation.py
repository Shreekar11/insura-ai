"""Unit tests for entity and relationship validation."""

import pytest
from app.services.extraction.entity_relationship_extractor import (
    EntityRelationshipExtractor,
    VALID_ENTITY_TYPES,
    VALID_RELATIONSHIP_TYPES
)


class TestEntityValidation:
    """Tests for entity validation logic."""
    
    @pytest.fixture
    def extractor(self):
        return EntityRelationshipExtractor(
            openrouter_api_key="test_key"
        )
    
    def test_valid_entity(self, extractor):
        """Test validation accepts valid entity."""
        entity = {
            "entity_type": "POLICY_NUMBER",
            "raw_value": "POL-123-456",
            "normalized_value": "POL123456",
            "confidence": 0.95
        }
        assert extractor._validate_entity(entity) is True
    
    def test_invalid_entity_type(self, extractor):
        """Test validation rejects invalid entity type."""
        entity = {
            "entity_type": "INVALID_TYPE",
            "raw_value": "test",
            "normalized_value": "test",
            "confidence": 0.95
        }
        assert extractor._validate_entity(entity) is False
    
    def test_missing_required_fields(self, extractor):
        """Test validation rejects entity missing required fields."""
        entity = {
            "entity_type": "POLICY_NUMBER",
            "raw_value": "POL-123-456",
            # Missing normalized_value and confidence
        }
        assert extractor._validate_entity(entity) is False
    
    def test_invalid_confidence_range(self, extractor):
        """Test validation rejects invalid confidence values."""
        # Confidence > 1.0
        entity1 = {
            "entity_type": "POLICY_NUMBER",
            "raw_value": "POL-123-456",
            "normalized_value": "POL123456",
            "confidence": 1.5
        }
        assert extractor._validate_entity(entity1) is False
        
        # Confidence < 0.0
        entity2 = {
            "entity_type": "POLICY_NUMBER",
            "raw_value": "POL-123-456",
            "normalized_value": "POL123456",
            "confidence": -0.1
        }
        assert extractor._validate_entity(entity2) is False
    
    def test_empty_values(self, extractor):
        """Test validation rejects empty values."""
        entity = {
            "entity_type": "POLICY_NUMBER",
            "raw_value": "",
            "normalized_value": "POL123456",
            "confidence": 0.95
        }
        assert extractor._validate_entity(entity) is False
        
        entity2 = {
            "entity_type": "POLICY_NUMBER",
            "raw_value": "POL-123-456",
            "normalized_value": "   ",
            "confidence": 0.95
        }
        assert extractor._validate_entity(entity2) is False
    
    def test_all_valid_entity_types(self, extractor):
        """Test all valid entity types are accepted."""
        for entity_type in VALID_ENTITY_TYPES:
            entity = {
                "entity_type": entity_type,
                "raw_value": "test",
                "normalized_value": "test",
                "confidence": 0.9
            }
            assert extractor._validate_entity(entity) is True, f"Failed for {entity_type}"


class TestRelationshipValidation:
    """Tests for relationship validation logic."""
    
    @pytest.fixture
    def extractor(self):
        return EntityRelationshipExtractor(
            openrouter_api_key="test_key"
        )
    
    def test_valid_relationship(self, extractor):
        """Test validation accepts valid relationship."""
        relationship = {
            "type": "HAS_INSURED",
            "source_type": "POLICY_NUMBER",
            "source_value": "POL123456",
            "target_type": "INSURED_NAME",
            "target_value": "John Doe",
            "confidence": 0.90
        }
        assert extractor._validate_relationship(relationship) is True
    
    def test_invalid_relationship_type(self, extractor):
        """Test validation rejects invalid relationship type."""
        relationship = {
            "type": "INVALID_RELATIONSHIP",
            "source_type": "POLICY_NUMBER",
            "source_value": "POL123456",
            "target_type": "INSURED_NAME",
            "target_value": "John Doe",
            "confidence": 0.90
        }
        assert extractor._validate_relationship(relationship) is False
    
    def test_invalid_source_entity_type(self, extractor):
        """Test validation rejects invalid source entity type."""
        relationship = {
            "type": "HAS_INSURED",
            "source_type": "INVALID_TYPE",
            "source_value": "POL123456",
            "target_type": "INSURED_NAME",
            "target_value": "John Doe",
            "confidence": 0.90
        }
        assert extractor._validate_relationship(relationship) is False
    
    def test_invalid_target_entity_type(self, extractor):
        """Test validation rejects invalid target entity type."""
        relationship = {
            "type": "HAS_INSURED",
            "source_type": "POLICY_NUMBER",
            "source_value": "POL123456",
            "target_type": "INVALID_TYPE",
            "target_value": "John Doe",
            "confidence": 0.90
        }
        assert extractor._validate_relationship(relationship) is False
    
    def test_missing_required_fields(self, extractor):
        """Test validation rejects relationship missing required fields."""
        relationship = {
            "type": "HAS_INSURED",
            "source_type": "POLICY_NUMBER",
            # Missing other fields
        }
        assert extractor._validate_relationship(relationship) is False
    
    def test_invalid_confidence_range(self, extractor):
        """Test validation rejects invalid confidence values."""
        relationship = {
            "type": "HAS_INSURED",
            "source_type": "POLICY_NUMBER",
            "source_value": "POL123456",
            "target_type": "INSURED_NAME",
            "target_value": "John Doe",
            "confidence": 1.5
        }
        assert extractor._validate_relationship(relationship) is False
    
    def test_empty_values(self, extractor):
        """Test validation rejects empty values."""
        relationship = {
            "type": "HAS_INSURED",
            "source_type": "POLICY_NUMBER",
            "source_value": "",
            "target_type": "INSURED_NAME",
            "target_value": "John Doe",
            "confidence": 0.90
        }
        assert extractor._validate_relationship(relationship) is False
    
    def test_all_valid_relationship_types(self, extractor):
        """Test all valid relationship types are accepted."""
        for rel_type in VALID_RELATIONSHIP_TYPES:
            relationship = {
                "type": rel_type,
                "source_type": "POLICY_NUMBER",
                "source_value": "test",
                "target_type": "INSURED_NAME",
                "target_value": "test",
                "confidence": 0.9
            }
            assert extractor._validate_relationship(relationship) is True, f"Failed for {rel_type}"


class TestValidationIntegration:
    """Integration tests for validation in parsing."""
    
    @pytest.fixture
    def extractor(self):
        return EntityRelationshipExtractor(
            openrouter_api_key="test_key"
        )
    
    def test_parse_filters_invalid_entities(self, extractor):
        """Test that parsing filters out invalid entities."""
        response = """{
            "entities": [
                {
                    "entity_type": "POLICY_NUMBER",
                    "raw_value": "POL-123",
                    "normalized_value": "POL123",
                    "confidence": 0.95
                },
                {
                    "entity_type": "INVALID_TYPE",
                    "raw_value": "test",
                    "normalized_value": "test",
                    "confidence": 0.9
                }
            ],
            "relationships": []
        }"""
        
        result = extractor._parse_extraction_response(response)
        
        # Should only have 1 valid entity
        assert len(result["entities"]) == 1
        assert result["entities"][0]["entity_type"] == "POLICY_NUMBER"
    
    def test_parse_filters_invalid_relationships(self, extractor):
        """Test that parsing filters out invalid relationships."""
        response = """{
            "entities": [],
            "relationships": [
                {
                    "type": "HAS_INSURED",
                    "source_type": "POLICY_NUMBER",
                    "source_value": "POL123",
                    "target_type": "INSURED_NAME",
                    "target_value": "John Doe",
                    "confidence": 0.9
                },
                {
                    "type": "INVALID_RELATIONSHIP",
                    "source_type": "POLICY_NUMBER",
                    "source_value": "POL123",
                    "target_type": "INSURED_NAME",
                    "target_value": "John Doe",
                    "confidence": 0.9
                }
            ]
        }"""
        
        result = extractor._parse_extraction_response(response)
        
        # Should only have 1 valid relationship
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["type"] == "HAS_INSURED"
