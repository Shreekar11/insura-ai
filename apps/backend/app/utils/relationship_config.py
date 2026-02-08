"""Relationship extraction configuration and semantic section pairings.

This module contains static configuration data for semantic batch relationship extraction,
including section pairings that define how insurance document sections are grouped for
relationship discovery.
"""

from typing import List, Dict, Any


# Semantic Section Pairings for Relationship Extraction
#
# Each pairing groups sections that have known relationship bridges, enabling
# the LLM to discover relationships within and across semantic groups.
#
# Strategic overlap (declarations + key sections) enables cross-batch relationship
# discovery while maintaining token efficiency.
SECTION_PAIRINGS: List[Dict[str, Any]] = [
    {
        "name": "policy_core",
        "description": "Policy issuance and core coverages",
        "sections": ["declarations", "coverages", "insuring_agreement", "coverage_grant", "coverage_extension"],
        "table_types": ["coverage_schedule", "premium_schedule"],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["HAS_INSURED", "ISSUED_BY", "BROKERED_BY", "HAS_COVERAGE", "HAS_ADDITIONAL_INSURED"],
        "priority": 1,
    },
    {
        "name": "coverage_modifiers",
        "description": "Coverage conditions, exclusions, and definitions",
        "sections": ["declarations", "coverages", "conditions", "exclusions", "definitions", "deductibles", "limits"],  # Added declarations for cross-pairing
        "table_types": [],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["SUBJECT_TO", "EXCLUDES", "DEFINED_IN", "HAS_CONDITION", "APPLIES_TO", "HAS_COVERAGE"],  # Added HAS_COVERAGE
        "priority": 2,
    },
    {
        "name": "locations",
        "description": "Property locations from SOV",
        "sections": ["declarations", "coverages"],  # Added coverages for location-coverage relationships
        "table_types": ["property_sov"],
        "include_sov": True,
        "include_loss_runs": False,
        "expected_rels": ["HAS_LOCATION", "APPLIES_TO", "LOCATED_AT", "HAS_COVERAGE"],  # Added HAS_COVERAGE
        "priority": 2,
    },
    {
        "name": "claims",
        "description": "Loss run claims history",
        "sections": ["declarations", "coverages"],  # Added coverages for claim-coverage relationships
        "table_types": ["loss_run"],
        "include_sov": False,
        "include_loss_runs": True,
        "expected_rels": ["HAS_CLAIM", "OCCURRED_AT", "APPLIES_TO", "HAS_COVERAGE"],  # Added cross-pairing rels
        "priority": 3,
    },
    {
        "name": "endorsements",
        "description": "Policy modifications via endorsements",
        "sections": ["declarations", "endorsements", "coverages"],  # Added coverages
        "table_types": [],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["MODIFIED_BY", "APPLIES_TO", "HAS_COVERAGE"],  # Added cross-pairing rels
        "priority": 3,
    },
    {
        "name": "auto_specifics",
        "description": "Auto insurance vehicles and drivers",
        "sections": ["declarations", "vehicle_details", "driver_information", "vehicle_information", "auto_coverages", "liability_coverages", "insured_declared_value"],  # Added declarations
        "table_types": [],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["HAS_VEHICLE", "OPERATED_BY", "INSURES_VEHICLE", "HAS_COVERAGE", "HAS_INSURED"],  # Added cross-pairing rels
        "priority": 2,
    },
    {
        "name": "property_specifics",
        "description": "Property details and construction",
        "sections": ["declarations", "building_information", "property_details", "construction_details", "property_coverages", "location_details"],  # Added declarations
        "table_types": [],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["HAS_LOCATION", "APPLIES_TO", "HAS_COVERAGE", "HAS_INSURED"],  # Added cross-pairing rels
        "priority": 2,
    },
    {
        "name": "workers_comp",
        "description": "Workers compensation class codes and payroll",
        "sections": ["declarations", "class_codes", "payroll_information", "experience_modification"],  # Added declarations
        "table_types": [],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["HAS_COVERAGE", "APPLIES_TO", "HAS_INSURED"],  # Added HAS_INSURED
        "priority": 3,
    },
    {
        "name": "financial",
        "description": "Premium and billing information",
        "sections": ["declarations", "premium_summary", "financial_statement", "premium_breakdown", "payment_schedule", "billing_information", "premium"],  # Already has declarations
        "table_types": ["premium_schedule"],
        "include_sov": False,
        "include_loss_runs": False,
        "expected_rels": ["BROKERED_BY", "ISSUED_BY", "HAS_INSURED"],  # Added HAS_INSURED
        "priority": 4,
    },
]
