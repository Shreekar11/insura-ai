"""Contracts (input/output schemas) for Enriched stage."""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ResolutionResult:
    """Result from canonical entity resolution."""
    resolved_count: int
    new_entities: int
    resolution_map: Dict[str, str]


@dataclass
class RelationshipResult:
    """Result from relationship extraction."""
    total_relationships: int
    relationship_types: List[str]
    connection_details: Dict[str, Any]
