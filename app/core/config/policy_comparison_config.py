"""Configuration for Policy Comparison workflow.

This module contains all configurable parameters for the Policy Comparison workflow,
making it easy to adjust behavior across different lines of business without code changes.
"""

import os
from typing import Literal

# Pre-flight Validation Configuration

# Required sections for policy comparison
REQUIRED_SECTIONS: list[str] = [
    "declarations",
    "coverages",
    "endorsements",
    "exclusions",
    "conditions",
]

# Required entity types for pre-flight validation
REQUIRED_ENTITIES: list[str] = [
    "POLICY_NUMBER",
    "INSURED_NAME",
    "EFFECTIVE_DATE",
    "EXPIRATION_DATE",
    "LIMIT_OCCURRENCE",
    "LIMIT_AGGREGATE",
    "DEDUCTIBLE_AMOUNT",
    "PREMIUM_TOTAL",
    "COINSURANCE_PCT",
]

# Fuzzy matching threshold for insured name comparison (0.0-1.0)
# Higher values require closer matches
INSURED_NAME_MATCH_THRESHOLD: float = float(
    os.getenv("POLICY_COMPARISON_INSURED_MATCH_THRESHOLD", "0.9")
)


# Minimum confidence score for section alignment (0.0-1.0)
ALIGNMENT_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("POLICY_COMPARISON_ALIGNMENT_THRESHOLD", "0.7")
)

# Alignment methods priority order
ALIGNMENT_METHODS: list[Literal["direct", "semantic", "fuzzy_match"]] = [
    "direct",      # Exact section type match
    "semantic",    # Embedding-based similarity
    "fuzzy_match", # Fuzzy string matching
]

# Numeric Diff Configuration
NUMERIC_FIELDS_CONFIG: dict[str, dict[str, float]] = {
    "limit_occurrence": {
        "low": 5.0,      # < 5% change
        "medium": 15.0,  # 5-15% change
        "high": 15.0,    # > 15% change
    },
    "limit_aggregate": {
        "low": 5.0,
        "medium": 15.0,
        "high": 15.0,
    },
    "deductible_amount": {
        "low": 10.0,
        "medium": 25.0,
        "high": 25.0,
    },
    "premium_total": {
        "low": 5.0,
        "medium": 10.0,
        "high": 10.0,
    },
    "coinsurance_pct": {
        "low": 5.0,
        "medium": 10.0,
        "high": 10.0,
    },
}

# Field paths for nested JSONB extraction
# Maps display names to JSONB paths
FIELD_PATHS: dict[str, list[str]] = {
    "limit_occurrence": ["limit_occurrence", "limits", "occurrence_limit"],
    "limit_aggregate": ["limit_aggregate", "limits", "aggregate_limit"],
    "deductible_amount": ["deductible_amount", "deductible", "amount"],
    "premium_total": ["premium_total", "premium", "total_premium"],
    "coinsurance_pct": ["coinsurance_pct", "coinsurance", "percentage"],
}

# Workflow Output Configuration
MINIMUM_CONFIDENCE_FOR_COMPLETION: float = float(
    os.getenv("POLICY_COMPARISON_MIN_CONFIDENCE", "0.75")
)

# Maximum number of high severity changes before triggering NEEDS_REVIEW
MAX_HIGH_SEVERITY_CHANGES: int = int(
    os.getenv("POLICY_COMPARISON_MAX_HIGH_SEVERITY", "5")
)

# Coverage Matching Configuration
COVERAGE_NAME_MATCH_THRESHOLD: float = float(
    os.getenv("POLICY_COMPARISON_COVERAGE_MATCH_THRESHOLD", "0.85")
)

# Coverage types to prioritize in comparison
PRIORITY_COVERAGE_TYPES: list[str] = [
    "property",
    "business_income",
    "equipment_breakdown",
    "general_liability",
]

# Conditional Processing Configuration
REQUIRED_STAGES: list[str] = [
    "processed",   # OCR, page analysis, chunking
    "extracted",   # Section field extraction
    "enriched",    # Entity resolution
]

# Whether to automatically trigger missing stages
AUTO_TRIGGER_MISSING_STAGES: bool = os.getenv(
    "POLICY_COMPARISON_AUTO_TRIGGER_STAGES", "true"
).lower() == "true"

WORKFLOW_NAME: str = "policy_comparison"
WORKFLOW_VERSION: str = "v1"
WORKFLOW_DISPLAY_NAME: str = "Policy Comparison"
WORKFLOW_DESCRIPTION: str = (
    "Compare two insurance policy documents to identify material changes "
    "in coverage, limits, deductibles, and premiums"
)
