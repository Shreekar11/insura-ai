import pytest
import json
from unittest.mock import AsyncMock, patch
from decimal import Decimal
from app.services.product.quote_comparison.reasoning_service import QuoteComparisonReasoningService
from app.schemas.product.quote_comparison import (
    MaterialDifference,
    CoverageComparisonRow,
    QuoteComparisonSummary,
    QuoteComparisonResult,
    PricingAnalysis
)

@pytest.fixture
def reasoning_service():
    with patch("app.services.product.quote_comparison.reasoning_service.UnifiedLLMClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_class.return_value = mock_client_instance
        service = QuoteComparisonReasoningService()
        return service

@pytest.mark.asyncio
async def test_enrich_material_differences(reasoning_service):
    differences = [
        MaterialDifference(
            field_name="location_address",
            section_type="declarations",
            quote1_value="123 Main St",
            quote2_value="123 Main St",
            change_type="identical",
            severity="low"
        ),
        MaterialDifference(
            field_name="limit_occurrence",
            section_type="coverages",
            quote1_value=1000000,
            quote2_value=2000000,
            change_type="increase",
            severity="medium"
        )
    ]

    # Mock LLM Response for the second diff
    resp = [{"id": id(differences[1]), "reason": "Reason for limit increase"}]
    reasoning_service.client.generate_content.return_value = json.dumps(resp)

    enriched = await reasoning_service.enrich_material_differences(differences)

    assert len(enriched) == 2
    # Check deterministic logic for identical
    assert "Found location address in both Quotes as same" in enriched[0].broker_note
    # Check LLM logic for difference
    assert enriched[1].broker_note == "Reason for limit increase"

@pytest.mark.asyncio
async def test_enrich_coverage_rows(reasoning_service):
    rows = [
        CoverageComparisonRow(
            canonical_coverage="dwelling",
            category="property",
            quote1_present=True,
            quote1_limit=Decimal("500000"),
            quote1_deductible=Decimal("1000"),
            quote2_present=True,
            quote2_limit=Decimal("500000"),
            quote2_deductible=Decimal("1000")
        ),
        CoverageComparisonRow(
            canonical_coverage="personal_liability",
            category="liability",
            quote1_present=True,
            quote1_limit=Decimal("300000"),
            quote2_present=True,
            quote2_limit=Decimal("500000"),
            limit_difference=Decimal("200000"),
            limit_advantage="quote2"
        )
    ]

    enriched = await reasoning_service.enrich_coverage_rows(rows)

    assert len(enriched) == 2
    assert "identical limits and deductibles for dwelling" in enriched[0].broker_note
    assert "$200,000 advantageous difference in limits" in enriched[1].broker_note

@pytest.mark.asyncio
async def test_generate_overall_summary(reasoning_service):
    summary = QuoteComparisonSummary(
        total_coverages_compared=10,
        coverage_gaps_count=1,
        material_differences_count=2,
        high_severity_count=0,
        overall_confidence=Decimal("0.9"),
        comparison_scope="full"
    )
    
    result = QuoteComparisonResult(
        comparison_summary=summary,
        comparison_matrix=[],
        coverage_gaps=[],
        material_differences=[
            MaterialDifference(
                field_name="limit_occurrence",
                section_type="coverages",
                quote1_value=1000000,
                quote2_value=2000000,
                change_type="increase",
                severity="high"
            )
        ],
        pricing_analysis=PricingAnalysis(
            quote1_total_premium=Decimal("1000"),
            quote2_total_premium=Decimal("1100"),
            premium_difference=Decimal("100"),
            premium_percent_change=Decimal("10"),
            lower_premium_quote="quote1"
        )
    )
    
    reasoning_service.client.generate_content.return_value = "Everything looks good."
    
    summary_text = await reasoning_service.generate_overall_summary(result)
    assert summary_text == "Everything looks good."
