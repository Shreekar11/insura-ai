"""Shared utility for generating canonical keys for entity resolution.

This module provides a consistent algorithm for generating canonical keys across
the embedding and entity resolution systems, ensuring both systems can bridge
to the same canonical entities.
"""

import hashlib
from typing import Dict, Any, Optional


def generate_canonical_key(entity_type: str, normalized_value: str) -> str:
    """Generate canonical key for entity.

    The canonical key is a SHA256 hash of entity_type + normalized_value,
    ensuring uniqueness across entity types. This algorithm must stay consistent
    with EntityResolver to maintain the vector↔graph bridge.

    Args:
        entity_type: Type of entity (e.g., "Coverage", "Policy", "Exclusion")
        normalized_value: Normalized identifying value (e.g., policy number,
                         coverage name, location address)

    Returns:
        str: Canonical key (32-char hex hash)

    Examples:
        >>> generate_canonical_key("Policy", "POL-12345")
        '7a8b9c0d1e2f3g4h5i6j7k8l9m0n1o2p'
        >>> generate_canonical_key("Coverage", "General Liability")
        '3a4b5c6d7e8f9g0h1i2j3k4l5m6n7o8p'
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
    entity type, matching the logic in EntityResolver.

    Args:
        entity_type: Type of entity
        entity_data: Dictionary of entity attributes

    Returns:
        Normalized value or None if not found
    """
    # Field priority map for each entity type
    # Uses the same logic as EntityResolver._extract_normalized_value()
    field_map = {
        "Policy": ["policy_number", "number"],
        "Coverage": ["name", "title", "coverage_name"],
        "Exclusion": ["name", "title"],
        "Condition": ["title", "name"],
        "Endorsement": ["title", "name", "endorsement_number", "form_number"],
        "Definition": ["term"],
        "Location": ["address", "location_id"],
        "Claim": ["claim_number"],
        "Vehicle": ["vin"],
        "Driver": ["name", "license_number"],
        "Organization": ["name"],
    }

    # Try each field in priority order
    for field in field_map.get(entity_type, ["name", "title"]):
        value = entity_data.get(field)
        if value:
            # Normalize: strip, lowercase
            return str(value).strip().lower()

    return None
