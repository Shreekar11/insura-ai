"""Attribute normalizer for standardizing entity attributes across the extraction pipeline.

This module provides utilities to normalize entity attributes to a consistent schema,
ensuring that coverage and exclusion entities have standardized field names
regardless of how they were extracted.
"""

from typing import Dict, Any, Optional, List


# Standard coverage attribute names
COVERAGE_ATTRIBUTE_MAPPING = {
    # Name variations -> coverage_name
    "name": "coverage_name",
    "title": "coverage_name",
    "coverage_title": "coverage_name",
    "cov_name": "coverage_name",

    # Type variations -> coverage_type
    "type": "coverage_type",
    "cov_type": "coverage_type",

    # Category variations -> coverage_category
    "category": "coverage_category",
    "cov_category": "coverage_category",

    # Description variations -> description
    "summary": "description",
    "coverage_description": "description",
    "details": "description",

    # Limit variations -> limit_amount
    "limit": "limit_amount",
    "coverage_limit": "limit_amount",
    "policy_limit": "limit_amount",

    # Deductible variations -> deductible_amount
    "deductible": "deductible_amount",
    "ded_amount": "deductible_amount",
}


# Standard exclusion attribute names
EXCLUSION_ATTRIBUTE_MAPPING = {
    # Name variations -> exclusion_name
    "name": "exclusion_name",
    "title": "exclusion_name",
    "exclusion_title": "exclusion_name",
    "excl_name": "exclusion_name",

    # Type variations -> exclusion_type
    "type": "exclusion_type",
    "excl_type": "exclusion_type",

    # Scope variations -> scope
    "exclusion_scope": "scope",
    "applies_to": "scope",

    # Description variations -> description
    "summary": "description",
    "exclusion_description": "description",
    "details": "description",

    # Severity variations -> severity
    "impact": "severity",
    "materiality": "severity",
}


def normalize_coverage_attributes(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize coverage entity attributes to standard schema.

    Args:
        entity: Coverage entity dict with potentially non-standard attribute names.

    Returns:
        Entity dict with standardized attribute names.
    """
    normalized = {}

    # Handle attributes dict if present
    source = entity.get("attributes", entity)

    for key, value in source.items():
        # Map to standard name if applicable
        standard_key = COVERAGE_ATTRIBUTE_MAPPING.get(key.lower(), key)

        # Don't overwrite if standard name already exists with a value
        if standard_key in normalized and normalized[standard_key]:
            continue

        normalized[standard_key] = value

    # Ensure coverage_name exists
    if "coverage_name" not in normalized or not normalized["coverage_name"]:
        # Try to extract from various sources
        normalized["coverage_name"] = (
            entity.get("coverage_name") or
            entity.get("name") or
            entity.get("title") or
            "Unknown Coverage"
        )

    # Copy over non-attribute fields from original entity
    for key in ["id", "type", "confidence", "entity_id"]:
        if key in entity and key not in normalized:
            normalized[key] = entity[key]

    return normalized


def normalize_exclusion_attributes(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize exclusion entity attributes to standard schema.

    Args:
        entity: Exclusion entity dict with potentially non-standard attribute names.

    Returns:
        Entity dict with standardized attribute names.
    """
    normalized = {}

    # Handle attributes dict if present
    source = entity.get("attributes", entity)

    for key, value in source.items():
        # Map to standard name if applicable
        standard_key = EXCLUSION_ATTRIBUTE_MAPPING.get(key.lower(), key)

        # Don't overwrite if standard name already exists with a value
        if standard_key in normalized and normalized[standard_key]:
            continue

        normalized[standard_key] = value

    # Ensure exclusion_name exists
    if "exclusion_name" not in normalized or not normalized["exclusion_name"]:
        # Try to extract from various sources
        normalized["exclusion_name"] = (
            entity.get("exclusion_name") or
            entity.get("title") or
            entity.get("name") or
            "Unknown Exclusion"
        )

    # Copy over non-attribute fields from original entity
    for key in ["id", "type", "confidence", "entity_id"]:
        if key in entity and key not in normalized:
            normalized[key] = entity[key]

    return normalized


def normalize_entity_list(
    entities: List[Dict[str, Any]],
    entity_type: str,
) -> List[Dict[str, Any]]:
    """Normalize a list of entities based on their type.

    Args:
        entities: List of entity dicts.
        entity_type: Type of entities ("coverage" or "exclusion").

    Returns:
        List of normalized entity dicts.
    """
    if not entities:
        return []

    normalizer = (
        normalize_coverage_attributes
        if entity_type.lower() == "coverage"
        else normalize_exclusion_attributes
    )

    return [normalizer(entity) for entity in entities]


def extract_entity_name(entity: Dict[str, Any], entity_type: str) -> Optional[str]:
    """Extract the name from an entity regardless of attribute naming convention.

    Args:
        entity: Entity dict.
        entity_type: Type of entity ("coverage" or "exclusion").

    Returns:
        Entity name or None.
    """
    # Check top-level attributes first
    if entity_type.lower() == "coverage":
        name = entity.get("coverage_name")
    else:
        name = entity.get("exclusion_name") or entity.get("title")

    if name:
        return name

    # Check in attributes dict
    attrs = entity.get("attributes", {})
    if entity_type.lower() == "coverage":
        name = (
            attrs.get("coverage_name") or
            attrs.get("name") or
            attrs.get("title")
        )
    else:
        name = (
            attrs.get("exclusion_name") or
            attrs.get("title") or
            attrs.get("name")
        )

    if name:
        return name

    # Fallback to generic fields
    return entity.get("name") or entity.get("title")


def extract_entity_description(entity: Dict[str, Any]) -> Optional[str]:
    """Extract description from an entity regardless of attribute naming.

    Args:
        entity: Entity dict.

    Returns:
        Description or None.
    """
    # Check top-level first
    description = entity.get("description") or entity.get("summary")
    if description:
        return description

    # Check attributes
    attrs = entity.get("attributes", {})
    return attrs.get("description") or attrs.get("summary") or attrs.get("details")
