"""Shared utility for generating canonical keys for entity resolution.

This module provides a consistent algorithm for generating canonical keys across
the embedding and entity resolution systems, ensuring both systems can bridge
to the same canonical entities.
"""

import hashlib
import re
from typing import Dict, Any, Optional


def slugify_entity_id(text: str, prefix: Optional[str] = None) -> str:
    """Normalize text for use as a stable entity identifier (slug).

    Converts text to snake_case, removes special characters, and handles
    consecutive underscores. This matches the logic in EntitySynthesizer.

    Args:
        text: Text to normalize (e.g., "Expected Or Intended Injury")
        prefix: Optional prefix for the ID (e.g., "excl")

    Returns:
        str: Slugified identifier (e.g., "excl_expected_or_intended_injury")
    """
    if not text:
        return ""

    # Convert to lowercase and replace spaces/hyphens/slashes with underscores
    normalized = text.lower().replace(' ', '_').replace('-', '_').replace('/', '_')
    
    # Remove all characters that are not alphanumeric or underscore
    normalized = ''.join(c if c.isalnum() or c == '_' else '_' for c in normalized)
    
    # Collapse multiple consecutive underscores into one
    while '__' in normalized:
        normalized = normalized.replace('__', '_')
    
    # Strip leading/trailing underscores
    normalized = normalized.strip('_')
    
    return f"{prefix}_{normalized}" if prefix else normalized


def generate_canonical_key(entity_type: str, normalized_value: str) -> str:
    """Generate canonical key for entity.

    The canonical key is a SHA256 hash of entity_type + normalized_value,
    ensuring uniqueness across entity types. This algorithm is the source of truth
    for the vector↔graph bridge.

    Args:
        entity_type: Type of entity (e.g., "Coverage", "Policy", "Exclusion")
        normalized_value: Normalized identifying value (slugified if applicable)

    Returns:
        str: Canonical key (32-char hex hash)
    """
    # Use SHA256 hash of type:value (lowercase for normalization)
    key_input = f"{entity_type}:{normalized_value}".lower()
    return hashlib.sha256(key_input.encode()).hexdigest()[:32]


def extract_normalized_value(
    entity_type: str,
    entity_data: Dict[str, Any]
) -> Optional[str]:
    """Extract the normalized identifying value from entity data.

    This function knows which field to use as the canonical identifier for each
    entity type and applies slugification for prioritized entity types.

    Args:
        entity_type: Type of entity
        entity_data: Dictionary of entity attributes

    Returns:
        Normalized value or None if not found
    """
    # Field priority map for each entity type
    field_map = {
        "Policy": ["policy_number", "number"],
        "Coverage": ["name", "title", "coverage_name"],
        "Exclusion": ["title", "name", "exclusion_name"],
        "Condition": ["title", "name", "condition_title"],
        "Endorsement": ["title", "name", "form_number", "endorsement_number"],
        "Definition": ["term", "definition_term"],
        "Location": ["address", "location_id"],
        "Claim": ["claim_number", "loss_number"],
        "Vehicle": ["vin"],
        "Driver": ["name", "license_number"],
        "Organization": ["name"],
    }

    # Entity types that use slugified identifiers for canonical keys
    slug_prefix_map = {
        "Coverage": "cov",
        "Exclusion": "excl",
        "Condition": "cond",
        "Endorsement": "end",
        "Definition": "def",
    }

    # Try each field in priority order
    for field in field_map.get(entity_type, ["name", "title"]):
        value = entity_data.get(field)
        if value:
            # If it's a slugified type, use the slugifier
            if entity_type in slug_prefix_map:
                return slugify_entity_id(str(value), slug_prefix_map[entity_type])
            
            # Otherwise just strip and lowercase
            return str(value).strip().lower()

    return None
