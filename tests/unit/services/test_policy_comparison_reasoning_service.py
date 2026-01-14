import pytest
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from decimal import Decimal
from app.services.product.policy_comparison.reasoning_service import PolicyComparisonReasoningService
from app.schemas.workflows.policy_comparison import ComparisonChange, SectionProvenance

@pytest.fixture
def reasoning_service():
    with patch("app.services.product.policy_comparison.reasoning_service.UnifiedLLMClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance
        service = PolicyComparisonReasoningService()
        return service

@pytest.mark.asyncio
async def test_enrich_changes_with_reasoning(reasoning_service):
    # Mock data
    doc1_id = uuid4()
    doc2_id = uuid4()
    provenance = SectionProvenance(
        doc1_section_id=doc1_id,
        doc2_section_id=doc2_id,
        doc1_page_range={"start": 1, "end": 1},
        doc2_page_range={"start": 1, "end": 1},
    )
    
    changes = [
        ComparisonChange(
            field_name="limit_occurrence",
            section_type="coverages",
            coverage_name="General Liability",
            old_value=1000000,
            new_value=2000000,
            change_type="increase",
            severity="medium",
            provenance=provenance
        ),
        ComparisonChange(
            field_name="premium_total",
            section_type="declarations",
            old_value=5000,
            new_value=5500,
            change_type="increase",
            severity="low",
            provenance=provenance
        )
    ]

    # Mock LLM Response
    # In the real code, we use parse_json_safely which might return ints or strings
    resp1 = [{"id": id(changes[0]), "reason": "Reason for coverage change"}]
    resp2 = [{"id": id(changes[1]), "reason": "Reason for declaration change"}]
    
    reasoning_service.client.generate_content.side_effect = [
        json.dumps(resp1),
        json.dumps(resp2)
    ]

    # Run Enrichment
    enriched = await reasoning_service.enrich_changes_with_reasoning(changes)

    # Verification
    assert len(enriched) == 2
    assert enriched[0].reasoning == "Reason for coverage change"
    assert enriched[1].reasoning == "Reason for declaration change"
    assert reasoning_service.client.generate_content.call_count == 2

@pytest.mark.asyncio
async def test_generate_overall_explanation(reasoning_service):
    doc1_id = uuid4()
    doc2_id = uuid4()
    provenance = SectionProvenance(
        doc1_section_id=doc1_id,
        doc2_section_id=doc2_id,
        doc1_page_range={"start": 1, "end": 1},
        doc2_page_range={"start": 1, "end": 1},
    )
    
    changes = [
        ComparisonChange(
            field_name="limit_occurrence",
            section_type="coverages",
            old_value=1000000,
            new_value=2000000,
            change_type="increase",
            severity="high",
            provenance=provenance
        )
    ]
    
    reasoning_service.client.generate_content.return_value = "This is a great summary."
    
    summary = await reasoning_service.generate_overall_explanation(changes)
    
    assert summary == "This is a great summary."
    reasoning_service.client.generate_content.assert_called_once()
