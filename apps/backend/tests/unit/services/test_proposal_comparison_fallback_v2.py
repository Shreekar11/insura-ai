import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from decimal import Decimal

from app.services.product.proposal_generation.proposal_comparison_service import ProposalComparisonService

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def service(mock_session):
    return ProposalComparisonService(mock_session)

@pytest.mark.asyncio
async def test_fetch_and_normalize_data_with_fallback(service):
    # Mock Repositories
    service.section_repo = AsyncMock()
    service.entity_repo = AsyncMock()
    
    doc_id = uuid4()
    workflow_id = uuid4()
    
    # 1. Test Coverage Fallback
    # Section repo returns empty coverages
    section_output = MagicMock()
    section_output.display_payload = {"coverages": []}
    service.section_repo.get_by_document_and_section.return_value = section_output
    
    # Entity repo returns coverage entities
    entity1 = MagicMock()
    entity1.display_payload = {
        "attributes": {
            "coverage_name": "General Liability",
            "limit_amount": 1000000,
            "deductible_amount": 500
        }
    }
    entity2 = MagicMock()
    entity2.display_payload = {
        "attributes": {
            "coverage_name": "Property",
            "limit_amount": 500000
        }
    }
    service.entity_repo.get_by_document_and_type.return_value = [entity1, entity2]
    
    result = await service._fetch_and_normalize_data(doc_id, workflow_id, "coverages")
    
    assert result["General Liability"] == 1000000
    assert result["General Liability Deductible"] == 500
    assert result["Property"] == 500000
    service.entity_repo.get_by_document_and_type.assert_called_with(
        document_id=doc_id,
        entity_type="Coverage",
        workflow_id=workflow_id
    )

@pytest.mark.asyncio
async def test_fetch_and_normalize_data_no_fallback_needed(service):
    # Mock Repositories
    service.section_repo = AsyncMock()
    service.entity_repo = AsyncMock()
    
    doc_id = uuid4()
    workflow_id = uuid4()
    
    # Section repo returns data
    section_output = MagicMock()
    section_output.display_payload = {
        "coverages": [
            {
                "coverage_name": "General Liability",
                "limit_amount": 2000000
            }
        ]
    }
    service.section_repo.get_by_document_and_section.return_value = section_output
    
    result = await service._fetch_and_normalize_data(doc_id, workflow_id, "coverages")
    
    assert result["General Liability"] == 2000000
    service.entity_repo.get_by_document_and_type.assert_not_called()

@pytest.mark.asyncio
async def test_normalize_section_data_all_types(service):
    # Coverages
    cov_data = {
        "coverages": [
            {"coverage_name": "GL", "limit_amount": 100, "deductible_amount": 10},
            {"coverage_name": "Property", "premium_amount": 50}
        ]
    }
    normalized_cov = service._normalize_section_data("coverages", cov_data)
    assert normalized_cov["GL"] == 100
    assert normalized_cov["GL Deductible"] == 10
    assert normalized_cov["Property Premium"] == 50
    
    # Deductibles
    ded_data = {
        "deductibles": [
            {"deductible_name": "Wind/Hail", "amount": 5000},
            {"id": "ded_other", "amount": 1000}
        ]
    }
    normalized_ded = service._normalize_section_data("deductibles", ded_data)
    assert normalized_ded["Wind/Hail"] == 5000
    assert normalized_ded["ded_other"] == 1000
    
    # Exclusions
    excl_data = {
        "exclusions": [
            {"title": "War Exclusion"},
            {"id": "excl_cyber"}
        ]
    }
    normalized_excl = service._normalize_section_data("exclusions", excl_data)
    assert normalized_excl["War Exclusion"] == "Present"
    assert normalized_excl["excl_cyber"] == "Present"

    # Endorsements
    end_data = {
        "endorsements": [
            {"endorsement_name": "Add Insured"},
            {"id": "end_001"}
        ]
    }
    normalized_end = service._normalize_section_data("endorsements", end_data)
    assert normalized_end["Add Insured"] == "Present"
    assert normalized_end["end_001"] == "Present"

    # Declarations (Flat)
    decl_data = {
        "policy_number": "POL123",
        "insured_name": "Insured Co"
    }
    normalized_decl = service._normalize_section_data("declarations", decl_data)
    assert normalized_decl["policy_number"] == "POL123"
    assert normalized_decl["insured_name"] == "Insured Co"
