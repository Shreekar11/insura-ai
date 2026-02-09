import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from app.services.product.policy_comparison.entity_comparison_service import EntityComparisonService
from app.schemas.product.policy_comparison import EntityType, MatchType, ComparisonSource

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def service(mock_session):
    return EntityComparisonService(mock_session)

@pytest.mark.asyncio
async def test_endorsement_mode_unchanged(service):
    """Test that unmatched base entities are marked as UNCHANGED in endorsement mode."""
    # Mock data indicating doc2 is an endorsement
    doc1_data = {"entities": []}
    doc2_data = {
        "entities": [
            {
                "entity_type": "document_classification",
                "fields": [{"classification": "endorsement"}]
            }
        ]
    }
    
    doc1_coverages = [{"name": "Base Coverage", "canonical_id": "base-1", "_extraction_id": uuid4()}]
    doc2_coverages = [] # Missing in endorsement
    
    # Mock matcher service behavior
    service.matcher_service.match_entities = AsyncMock(return_value=[
        {
            "match_type": MatchType.UNCHANGED,
            "doc1_entity": doc1_coverages[0],
            "doc2_entity": None,
            "match_method": "endorsement_mode",
            "reasoning": "Standard provision from base document"
        }
    ])
    service.matcher_service.find_cross_type_matches = AsyncMock(return_value=[])
    
    with patch.object(service, '_extract_coverages', side_effect=[doc1_coverages, doc2_coverages]), \
         patch.object(service, '_extract_exclusions', return_value=[]), \
         patch.object(service, '_is_endorsement_only', return_value=True), \
         patch.object(service, '_get_document_name', return_value="Test Doc"), \
         patch.object(service, '_generate_overall_explanation', return_value="Summary"):
        
        result = await service.compare_entities(uuid4(), uuid4(), uuid4(), doc1_data, doc2_data)
        
        assert result.summary.coverages_unchanged == 1
        assert result.comparisons[0].match_type == MatchType.UNCHANGED
        assert result.comparisons[0].entity_name == "Base Coverage"

@pytest.mark.asyncio
async def test_cross_type_matching(service):
    """Test that cross-type matches are correctly detected and reported."""
    doc1_data = {"entities": []}
    doc2_data = {"entities": []}
    
    doc1_coverages = [{"name": "Hybrid Concept", "description": "Desc", "canonical_id": "c1", "_extraction_id": uuid4()}]
    doc2_coverages = []
    doc1_exclusions = []
    doc2_exclusions = [{"name": "Hybrid Concept", "description": "Desc", "canonical_id": "c1", "_extraction_id": uuid4()}]
    
    cross_match = {
        "doc1_entity": doc1_coverages[0],
        "doc2_entity": doc2_exclusions[0],
        "doc1_type": EntityType.COVERAGE,
        "doc2_type": EntityType.EXCLUSION,
        "confidence": Decimal("1.0"),
        "reasoning": "Reclassified from Coverage to Exclusion"
    }
    
    service.matcher_service.match_entities = AsyncMock(return_value=[])
    service.matcher_service.find_cross_type_matches = AsyncMock(return_value=[cross_match])
    
    with patch.object(service, '_extract_coverages', side_effect=[doc1_coverages, doc2_coverages]), \
         patch.object(service, '_extract_exclusions', side_effect=[doc1_exclusions, doc2_exclusions]), \
         patch.object(service, '_is_endorsement_only', return_value=False), \
         patch.object(service, '_get_document_name', return_value="Test Doc"), \
         patch.object(service, '_generate_overall_explanation', return_value="Summary"):
        
        result = await service.compare_entities(uuid4(), uuid4(), uuid4(), doc1_data, doc2_data)
        
        assert result.summary.entities_reclassified == 1
        assert result.comparisons[0].match_type == MatchType.TYPE_RECLASSIFIED
        assert result.comparisons[0].entity_name == "Hybrid Concept"
