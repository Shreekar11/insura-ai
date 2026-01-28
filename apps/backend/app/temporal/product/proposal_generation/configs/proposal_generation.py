"""Configuration for Proposal Generation Workflow."""

import os
from typing import Literal
import yaml
from pathlib import Path

# Path to the YAML template
CONFIG_PATH = Path(__file__).parent / "proposal_generation.yaml"

def load_proposal_generation_config():
    """Load proposal generation configuration from YAML."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    except Exception:
        return {}

CONFIG = load_proposal_generation_config()

# Required sections for proposal generation
REQUIRED_SECTIONS = [
    "declarations",
    "coverages",
    "deductibles",
    "premium",
    "exclusions",
    "endorsements",
]

# Required entities for proposal generation
REQUIRED_ENTITIES = [
    "policy_number",
    "insured_name",
    "effective_date",
    "expiration_date",
    "limit",
    "deductible",
    "premium_amount",
    "total_premium",
    "quote_number",
    "quote_id",
    "carrier_name",
    "insured_location",
    "mailing_address",
    "risk_type",
]

# Processing configuration
PROCESSING_CONFIG = CONFIG.get("document_processing", {}).get("ensure", {})

# Individual flags for backward compatibility or simple use cases
ENABLE_TABLE_EXTRACTION: bool = PROCESSING_CONFIG.get("table_extraction", False)
ENABLE_PAGE_ANALYSIS: bool = PROCESSING_CONFIG.get("page_analysis", True)
ENABLE_SECTION_EXTRACTION: bool = "section_extraction" in PROCESSING_CONFIG
ENABLE_ENRICHMENT: bool = "enrichment" in PROCESSING_CONFIG
ENABLE_INDEXING: bool = "indexing" in PROCESSING_CONFIG