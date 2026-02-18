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
async def test_extract_section_data(service):
    # Mock structured data from WorkflowService
    data = {
        "sections": [
            {
                "id": str(uuid4()),
                "section_type": "coverages",
                "fields": {
                    "items": [
                        {"name": "General Liability", "limit": "1M"}
                    ]
                },
                "confidence": Decimal("0.95"),
                "page_range": {"start": 1, "end": 2}
            }
        ],
        "entities": []
    }
    
    coverages = service._extract_section_data(data, "coverages")
    
    assert len(coverages) == 1
    assert coverages[0]["name"] == "General Liability"
    assert "_extraction_id" in coverages[0]
    assert coverages[0]["_confidence"] == Decimal("0.95")
    assert coverages[0]["_page_range"] == {"start": 1, "end": 2}

@pytest.mark.asyncio
async def test_extract_effective_entities(service):
    # Mock structured data from WorkflowService
    data = {
        "sections": [],
        "entities": [
            {
                "id": str(uuid4()),
                "entity_type": "effective_coverages",
                "fields": [
                    {"coverage_name": "GL", "limit_amount": 1000000}
                ],
                "confidence": Decimal("0.99")
            }
        ]
    }
    
    coverages = service._extract_coverages(data)
    
    assert len(coverages) == 1
    assert coverages[0]["coverage_name"] == "GL"
    assert "_extraction_id" in coverages[0]
    assert coverages[0]["_confidence"] == Decimal("0.99")

@pytest.mark.asyncio
async def test_create_entity_comparison_with_metadata(service):
    doc1_id = uuid4()
    doc2_id = uuid4()
    ext_id1 = uuid4()
    ext_id2 = uuid4()
    
    match = {
        "match_type": MatchType.PARTIAL_MATCH,
        "doc1_entity": {
            "name": "Old Coverage",
            "_extraction_id": ext_id1,
            "_confidence": Decimal("0.9"),
            "_page_range": {"start": 5, "end": 5}
        },
        "doc2_entity": {
            "name": "New Coverage",
            "_extraction_id": ext_id2,
            "_confidence": Decimal("0.95"),
            "_page_range": {"start": 6, "end": 6}
        },
        "field_differences": [{"field": "limit", "doc1_value": "1M", "doc2_value": "2M"}],
        "reasoning": "Limit increased"
    }
    
    comparison = service._create_entity_comparison(match, EntityType.SECTION_COVERAGE)
    
    assert comparison.entity_type == EntityType.SECTION_COVERAGE
    assert comparison.match_type == MatchType.PARTIAL_MATCH
    assert comparison.entity_name == "New Coverage"
    assert comparison.doc1_extraction_id == ext_id1
    assert comparison.doc2_extraction_id == ext_id2
    assert comparison.doc1_page_range == {"start": 5, "end": 5}
    assert comparison.doc2_page_range == {"start": 6, "end": 6}
    assert comparison.doc1_confidence == Decimal("0.9")
    assert comparison.doc2_confidence == Decimal("0.95")
    assert comparison.reasoning == "Limit increased"

@pytest.mark.asyncio
async def test_batched_summary_generation(service):
    import json
    # Mock comparisons
    comp1 = MagicMock()
    comp1.entity_type.value = "coverage"
    comp1.match_type.value = "partial_match"
    comp1.entity_name = "Coverage A"
    comp1.doc1_content = {"attr": "val1"}
    comp1.doc2_content = {"attr": "val2"}
    
    comp2 = MagicMock()
    comp2.entity_type.value = "exclusion"
    comp2.match_type.value = "added"
    comp2.entity_name = "Exclusion B"
    comp2.doc1_content = None
    comp2.doc2_content = {"attr": "val3"}
    
    comparisons = [comp1, comp2]
    
    # Mock LLM response
    mock_response = {
        "item_0": {
            "doc1_summary": "Summary 1.1",
            "doc2_summary": "Summary 1.2",
            "comparison_summary": "Comparison 1"
        },
        "item_1": {
            "doc1_summary": "",
            "doc2_summary": "Summary 2.2",
            "comparison_summary": "Comparison 2"
        }
    }
    
    service.llm_client.generate_content = AsyncMock(return_value=json.dumps(mock_response))
    
    # Run batching
    await service._generate_batched_summaries(comparisons)
    
    # Assert
    assert comp1.doc1_summary == "Summary 1.1"
    assert comp1.doc2_summary == "Summary 1.2"
    assert comp1.comparison_summary == "Comparison 1"
    assert comp1.reasoning == "Comparison 1"
    
    assert comp2.doc1_summary == ""
    assert comp2.doc2_summary == "Summary 2.2"
    assert comp2.comparison_summary == "Comparison 2"
    assert comp2.reasoning == "Comparison 2"
