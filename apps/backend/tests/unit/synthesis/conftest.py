"""Shared fixtures for synthesis tests."""

import pytest
from uuid import uuid4


@pytest.fixture
def sample_document_id():
    """Generate a sample document ID."""
    return uuid4()


@pytest.fixture
def sample_workflow_id():
    """Generate a sample workflow ID."""
    return uuid4()


@pytest.fixture
def full_extraction_result():
    """Complete extraction result with multiple section types."""
    return {
        "document_id": str(uuid4()),
        "section_results": [
            {
                "section_type": "declarations",
                "extracted_data": {
                    "policy_number": "POL-2024-001",
                    "insured_name": "ABC Corp",
                },
                "confidence": 0.95,
            },
            {
                "section_type": "endorsements",
                "extracted_data": {
                    "endorsements": [
                        {
                            "endorsement_name": "BUSINESS AUTO EXTENSION ENDORSEMENT",
                            "endorsement_type": "Add",
                            "impacted_coverage": "BUSINESS AUTO COVERAGE FORM",
                            "materiality": "Medium",
                        },
                        {
                            "endorsement_name": "BLANKET ADDITIONAL INSURED",
                            "endorsement_type": "Add",
                            "impacted_coverage": "BUSINESS AUTO COVERAGE FORM",
                            "materiality": "High",
                        },
                        {
                            "endorsement_name": "TEXAS WAIVER OF OUR RIGHT TO RECOVER",
                            "endorsement_type": "Restrict",
                            "impacted_coverage": "Workers Compensation",
                            "materiality": "High",
                        },
                    ]
                },
                "confidence": 0.9,
            },
        ],
        "all_entities": [],
        "total_tokens": 5000,
        "total_processing_time_ms": 3000,
    }


@pytest.fixture
def projection_extraction_result():
    """Extraction result with projection modifications."""
    return {
        "document_id": str(uuid4()),
        "section_results": [
            {
                "section_type": "endorsements",
                "extracted_data": {
                    "endorsements": [
                        {
                            "endorsement_number": "CA T4 52 02 16",
                            "endorsement_name": "Short Term Hired Auto",
                            "form_edition_date": "02 16",
                            "modifications": [
                                {
                                    "impacted_coverage": "Covered Autos Liability Coverage",
                                    "coverage_effect": "Expand",
                                    "effect_category": "expands_coverage",
                                    "scope_modification": "Extends coverage to non-owned autos for up to 30 days",
                                    "condition_modification": "Coverage limited to 30 days or less",
                                    "verbatim_language": "Coverage is extended...",
                                }
                            ],
                        }
                    ],
                    "all_modifications": [],
                },
                "confidence": 0.92,
            }
        ],
    }
