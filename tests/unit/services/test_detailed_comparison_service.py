import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from uuid import uuid4

from app.services.product.policy_comparison.detailed_comparison_service import DetailedComparisonService
from app.schemas.product.policy_comparison import SectionAlignment

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def service(mock_session):
    return DetailedComparisonService(mock_session)

@pytest.mark.asyncio
async def test_compute_comparison_dynamic(service):
    # Mock Repository
    mock_repo = AsyncMock()
    service.section_repo = mock_repo

    # Mock Data
    doc1_id = uuid4()
    doc2_id = uuid4()
    alignment = SectionAlignment(
        section_type="declarations",
        doc1_section_id=doc1_id,
        doc2_section_id=doc2_id,
        alignment_confidence=Decimal("0.9"),
        alignment_method="direct"
    )

    # Section 1 Data (Policy A)
    section1 = MagicMock()
    section1.id = doc1_id
    section1.page_range = {"start": 1, "end": 2}
    section1.extracted_fields = {
        "policy_number": "248600/31/201713426",
        "insured_name": "SH *PAVNISH KUMAR SHARMA*",
        "premium_total": 7222,
        "effective_date": "2017-12-22",
        "expiration_date": "2018-12-21",
        "address": {
             "city": "Jaipur",
             "line1": "Jaipur address" 
        },
        "extra_field": "Should be removed in B"
    }

    # Section 2 Data (Policy B)
    section2 = MagicMock()
    section2.id = doc2_id
    section2.page_range = {"start": 1, "end": 2}
    section2.extracted_fields = {
        "policy_number": "243600/31/2017/3426",
        "insured_name": "SH_PAVNISH KUMAR SHARMA_",
        "premium_total": 7725,
        "effective_date": "2016-12-22",
        "expiration_date": "2017-12-21",
        "address": {
             "city": "Jaipur",
             "line1": "Same address"
        },
        "new_field": "Added in B"
    }

    mock_repo.get_by_id.side_effect = lambda x: section1 if x == doc1_id else section2

    # Run Comparison
    changes = await service.compute_comparison([alignment])

    # Verification
    assert len(changes) > 0
    
    # Check Policy Number (Modified)
    pol_num = next(c for c in changes if c.field_name == "policy_number")
    assert pol_num.change_type == "modified"
    assert pol_num.old_value == "248600/31/201713426"

    # Check Insured Name (Formatting Diff)
    name = next(c for c in changes if c.field_name == "insured_name")
    assert name.change_type == "formatting_diff"
    
    # Check Premium (Numeric)
    prem = next(c for c in changes if c.field_name == "premium_total")
    assert prem.change_type == "increase"
    assert prem.absolute_change == 503
    assert prem.old_value == Decimal("7222")

    # Check Sequential Dates
    eff_date = next(c for c in changes if c.field_name == "effective_date")
    # 2017 vs 2016 is about 1 year apart
    # Wait, my logic checks if diff is 360-370 days.
    # 2017-12-22 - 2016-12-22 is exactly 365 days.
    assert eff_date.change_type == "sequential"

    # Check Added/Removed
    added = next(c for c in changes if c.field_name == "new_field")
    assert added.change_type == "added"

    removed = next(c for c in changes if c.field_name == "extra_field")
    assert removed.change_type == "removed"
    
    # Check Nested
    city = next(c for c in changes if c.field_name == "address.city")
    assert city.change_type == "no_change"
    assert city.new_value == "Jaipur"
    
    # Check Context Capture (Premium field in Declarations)
    # The declarations mock doesn't have a name field, but we can verify it's there
    prem = next(c for c in changes if c.field_name == "premium_total")
    assert prem.coverage_name is None # No identifier in parent dict
    
    # Let's add an identifier in a separate test or modify this one
