"""Configuration for Quote Comparison workflow.

This module contains all configurable parameters for the Quote Comparison workflow,
making it easy to adjust behavior across different lines of business without code changes.
"""

import os
from typing import Literal
import yaml
from pathlib import Path

# Path to the YAML template
CONFIG_PATH = Path(__file__).parent / "quote_comparison.yaml"


def load_quote_comparison_config():
    """Load quote comparison configuration from YAML."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


CONFIG = load_quote_comparison_config()


def normalize_name(name: str) -> str:
    """Normalize names to snake_case for consistency."""
    return name.lower().replace(" ", "_")


# Pre-flight Validation Configuration

# Required sections for quote comparison
_yaml_sections = CONFIG.get("document_processing", {}).get("indexing", {}).get("embeddings", {}).get("sections", [])
if not _yaml_sections:
    _yaml_sections = CONFIG.get("document_processing", {}).get("section_extraction", {}).get("sections", [])

REQUIRED_SECTIONS: list[str] = [normalize_name(s) for s in _yaml_sections] if _yaml_sections else [
    "premiums",
    "coverages",
    "conditions",
    "endorsements",
    "exclusions",
]

# Required entity types for pre-flight validation
_yaml_entities = CONFIG.get("document_processing", {}).get("enrichment", {}).get("entities", [])
REQUIRED_ENTITIES: list[str] = [normalize_name(e) for e in _yaml_entities] if _yaml_entities else [
    "carrier_name",
    "insured_name",
    "coverage_name",
    "limit",
    "deductible",
    "premium_amount",
    "effective_date",
    "expiration_date",
]

# Fuzzy matching threshold for insured name comparison (0.0-1.0)
INSURED_NAME_MATCH_THRESHOLD: float = float(
    os.getenv("QUOTE_COMPARISON_INSURED_MATCH_THRESHOLD", "0.9")
)

# Minimum confidence score for coverage alignment (0.0-1.0)
ALIGNMENT_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("QUOTE_COMPARISON_ALIGNMENT_THRESHOLD", "0.7")
)

# Alignment methods priority order
ALIGNMENT_METHODS: list[Literal["direct", "semantic", "fuzzy_match"]] = [
    "direct",
    "semantic",
    "fuzzy_match",
]

# Coverage Quality Scoring Configuration (PRD Section 7.4)
QUALITY_SCORE_WEIGHTS: dict[str, float] = {
    "coverage_presence": 1.0,
    "limit_adequacy": 0.8,
    "deductible_penalty": -0.3,
    "exclusion_risk": -0.4,
}

# Coverage Categories
COVERAGE_CATEGORIES: list[str] = [
    "property",
    "liability",
    "add_on",
]

# Numeric Diff Configuration (thresholds for severity)
NUMERIC_FIELDS_CONFIG: dict[str, dict[str, float]] = {
    "limit_amount": {
        "low": 5.0,
        "medium": 15.0,
        "high": 15.0,
    },
    "limit_per_occurrence": {
        "low": 5.0,
        "medium": 15.0,
        "high": 15.0,
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
    "premium_amount": {
        "low": 5.0,
        "medium": 10.0,
        "high": 10.0,
    },
    "total_premium": {
        "low": 5.0,
        "medium": 10.0,
        "high": 10.0,
    },
}

# Fields to exclude from dynamic comparison
EXCLUDED_FIELDS: set[str] = {
    "confidence",
    "metadata",
    "_meta",
    "source_page",
    "coordinates",
}

# Workflow Output Configuration
MINIMUM_CONFIDENCE_FOR_COMPLETION: float = float(
    os.getenv("QUOTE_COMPARISON_MIN_CONFIDENCE", "0.75")
)

# Maximum number of high severity changes before triggering NEEDS_REVIEW
MAX_HIGH_SEVERITY_CHANGES: int = int(
    os.getenv("QUOTE_COMPARISON_MAX_HIGH_SEVERITY", "5")
)

# Coverage Matching Configuration
COVERAGE_NAME_MATCH_THRESHOLD: float = float(
    os.getenv("QUOTE_COMPARISON_COVERAGE_MATCH_THRESHOLD", "0.85")
)

# Priority coverage types for comparison emphasis
PRIORITY_COVERAGE_TYPES: list[str] = [
    "dwelling",
    "property",
    "general_liability",
    "business_income",
]

# Conditional Processing Configuration
PROCESSING_CONFIG = CONFIG.get("document_processing", {}).get("ensure", {})

ENABLE_TABLE_EXTRACTION: bool = PROCESSING_CONFIG.get("table_extraction", False)
ENABLE_PAGE_ANALYSIS: bool = PROCESSING_CONFIG.get("page_analysis", True)
ENABLE_SECTION_EXTRACTION: bool = "section_extraction" in PROCESSING_CONFIG
ENABLE_ENRICHMENT: bool = "enrichment" in PROCESSING_CONFIG
ENABLE_INDEXING: bool = "indexing" in PROCESSING_CONFIG

REQUIRED_STAGES: list[str] = [
    "processed",
    "extracted",
    "enriched",
    "indexed",
    "summarized",
]

# Whether to automatically trigger missing stages
AUTO_TRIGGER_MISSING_STAGES: bool = os.getenv(
    "QUOTE_COMPARISON_AUTO_TRIGGER_STAGES", "true"
).lower() == "true"

# Workflow metadata
WORKFLOW_NAME: str = CONFIG.get("workflow", {}).get("name", "quote_comparison")
WORKFLOW_VERSION: str = CONFIG.get("workflow", {}).get("version", "v1")
WORKFLOW_DISPLAY_NAME: str = "Quote Comparison"
WORKFLOW_DESCRIPTION: str = CONFIG.get("workflow", {}).get("description", (
    "Compare multiple carrier quote packages by normalizing coverage data, "
    "evaluating adequacy, and producing side-by-side broker-facing outputs."
))

# Document limits (V1: 2 quotes only)
MIN_DOCUMENTS: int = CONFIG.get("workflow", {}).get("min_documents", 2)
MAX_DOCUMENTS: int = CONFIG.get("workflow", {}).get("max_documents", 2)
