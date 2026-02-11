"""
GraphRAG Retrieval Constants

This module contains constants for the GraphRAG retrieval system, including:
- Corrected Neo4j graph schema (node labels, edge types)
- Traversal configurations per intent type
- Intent-based section boost mappings
- Default retrieval parameters
- Insurance domain expansions

All constants are based on actual Neo4j graph data analysis (755 nodes, 112 edges, 19 workflows).
"""

from typing import Literal

# Node Labels
NODE_LABELS = [
    "VectorEmbedding",
    "Coverage",
    "Exclusion",
    "Endorsement",
    "Condition",
    "Definition",
    "Organization",
    "Location",
    "Policy",
    "Evidence",
    "Vehicle",
    "Driver",
    "Claim",
]

# Edge Types
EDGE_TYPES = [
    "HAS_COVERAGE",
    "MODIFIED_BY",
    "EXCLUDES",
    "SAME_AS",
    "SUBJECT_TO",
    "HAS_LOCATION",
    "HAS_INSURED",
    "BROKERED_BY",
    "APPLIES_TO",
    "ISSUED_BY",
    "HAS_ADDITIONAL_INSURED",
    "HAS_EMBEDDING",
    "SUPPORTED_BY",
    "HAS_CLAIM",
    "REFERENCES",
]

# Organization Role Values
ORGANIZATION_ROLES = [
    "insured",
    "carrier",
    "broker",
    "additional_insured",
]

# Traversal Configuration by Intent
TraversalConfig = dict[
    str, dict[str, int | list[str] | None]
]

TRAVERSAL_CONFIG: TraversalConfig = {
    "QA": {
        "max_depth": 2,
        "edge_types": [
            "HAS_COVERAGE",
            "EXCLUDES",
            "HAS_INSURED",
            "ISSUED_BY",
            "HAS_LOCATION",
            "DEFINED_IN",
            "SUPPORTED_BY",
            "REFERENCES",
        ],
        "max_nodes": 20,
        "description": "Factual queries - 2-hop traversal with foundational relationships",
    },
    "ANALYSIS": {
        "max_depth": 2,
        "edge_types": [
            "HAS_COVERAGE",
            "MODIFIED_BY",
            "EXCLUDES",
            "SUBJECT_TO",
            "APPLIES_TO",
            "SAME_AS",
            "HAS_INSURED",
            "BROKERED_BY",
        ],
        "max_nodes": 25,
        "description": "Comparative/analytical queries - 2-hop traversal",
    },
    "AUDIT": {
        "max_depth": 3,
        "edge_types": None,
        "max_nodes": 50,
        "description": "Provenance/evidence chains - 3+ hop traversal",
    },
}

# Intent-Based Section Boost Mappings
# Section type boost scores for intent-aware reranking
INTENT_SECTION_BOOSTS: dict[str, dict[str, float]] = {
    "QA": {
        "declarations": 0.15,
        "coverages": 0.12,
        "exclusions": 0.10,
        "schedule": 0.10,
        "policy_info": 0.08,
        "insured_info": 0.08,
        "conditions": 0.06,
        "definitions": 0.06,
    },
    "ANALYSIS": {
        "coverages": 0.15,
        "endorsements": 0.12,
        "exclusions": 0.10,
        "conditions": 0.08,
        "limits_deductibles": 0.08,
    },
    "AUDIT": {
        "endorsements": 0.15,
        "loss_run": 0.12,
        "claims": 0.10,
        "conditions": 0.08,
        "evidence": 0.08,
    },
}

# Entity type boost
ENTITY_MATCH_BOOST = 0.05

# Recency boost parameters
RECENCY_BOOST_MAX = 0.05
RECENCY_DECAY_DAYS = 365

# Default Retrieval Parameters
# Vector search defaults
DEFAULT_VECTOR_TOP_K = 20
DEFAULT_DISTANCE_THRESHOLD = 0.7
DEFAULT_SEMANTIC_WEIGHT = 0.7
DEFAULT_KEYWORD_WEIGHT = 0.3

# Context assembly defaults
DEFAULT_MAX_CONTEXT_TOKENS = 8000
DEFAULT_FULL_TEXT_COUNT = 5
DEFAULT_SUMMARY_MAX_TOKENS = 150

# LLM response generation defaults
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_MAX_TOKENS = 2000

# Abbreviation → full term mappings for query expansion
INSURANCE_EXPANSIONS: dict[str, list[str]] = {
    # Deductibles & Retentions
    "deductible": ["deductible", "self-insured retention", "SIR", "retention"],
    "SIR": ["SIR", "self-insured retention", "retention", "deductible"],
    # Bodily Injury & Property Damage
    "BI": ["BI", "bodily injury", "personal injury"],
    "PD": ["PD", "property damage", "physical damage"],
    "BIPD": ["BIPD", "bodily injury and property damage", "BI/PD"],
    # Liability Coverage Types
    "GL": ["GL", "general liability", "CGL", "commercial general liability"],
    "CGL": ["CGL", "commercial general liability", "GL", "general liability"],
    "AL": ["AL", "auto liability", "automobile liability"],
    "PL": ["PL", "professional liability", "E&O", "errors and omissions"],
    "E&O": ["E&O", "errors and omissions", "professional liability"],
    # Property Coverage
    "BPP": ["BPP", "business personal property"],
    "building": ["building", "structure", "premises"],
    # Workers Compensation
    "WC": ["WC", "workers compensation", "workers comp"],
    "EL": ["EL", "employers liability"],
    # Umbrella & Excess
    "umbrella": ["umbrella", "excess liability", "excess"],
    "excess": ["excess", "umbrella", "excess liability"],
    # Limits & Coverage Terms
    "per occurrence": ["per occurrence", "each occurrence", "per claim"],
    "aggregate": ["aggregate", "general aggregate", "total limit"],
    "CSL": ["CSL", "combined single limit"],
    "split limit": ["split limit", "split limits", "separate limits"],
    # Certificates & Documents
    "COI": ["COI", "certificate of insurance", "certificate"],
    "COB": ["COB", "certificate of occupancy"],
    "dec page": ["dec page", "declarations", "declaration page"],
    # Endorsements & Modifications
    "endorsement": ["endorsement", "rider", "addendum", "modification"],
    "rider": ["rider", "endorsement", "addendum"],
    # Claims & Losses
    "loss": ["loss", "claim", "incident"],
    "claim": ["claim", "loss", "incident"],
    # Additional Insureds
    "AI": ["AI", "additional insured", "additional named insured"],
    "additional insured": ["additional insured", "AI", "named insured"],
    # Named Insured
    "NI": ["NI", "named insured"],
    # Policy Types
    "CMP": ["CMP", "commercial multi-peril", "package policy"],
    "BOP": ["BOP", "business owners policy", "businessowners"],
    # Exclusions
    "exclusion": ["exclusion", "excluded", "not covered"],
    # Conditions
    "condition": ["condition", "requirement", "provision"],
}

# Common query patterns that should trigger specific section filters
QUERY_PATTERN_SECTION_HINTS: dict[str, list[str]] = {
    "deductible": ["coverages", "declarations", "limits_deductibles"],
    "limit": ["coverages", "declarations", "limits_deductibles"],
    "coverage": ["coverages", "schedule"],
    "exclusion": ["exclusions"],
    "exclude": ["exclusions"],
    "endorsement": ["endorsements"],
    "endorsements": ["endorsements"],
    "modification": ["endorsements"],
    "insured": ["insured_info", "declarations"],
    "carrier": ["policy_info", "declarations"],
    "broker": ["policy_info"],
    "location": ["locations", "schedule"],
    "premium": ["declarations", "policy_info"],
    "effective date": ["declarations", "policy_info"],
    "expiration": ["declarations", "policy_info"],
    "claim": ["claims", "loss_run"],
    "loss": ["claims", "loss_run"],
    "declaration": ["declarations"],
    "declarations": ["declarations"],
}

# Cypher query template for node mapping
NODE_MAPPING_QUERY = """
MATCH (e)
WHERE ANY(vid IN e.vector_entity_ids WHERE vid IN $entity_ids)
  AND e.workflow_id = $workflow_id
RETURN e as node, labels(e) as labels, elementId(e) as node_id
"""

# Cypher query template for adaptive traversal
# Note: edge_filter will be dynamically constructed based on intent
TRAVERSAL_QUERY_TEMPLATE = """
MATCH (start)
WHERE start.id IN $start_entity_ids
  AND start.workflow_id = $workflow_id
MATCH path = (start)-[{edge_filter}]-(related)
WHERE related.workflow_id = $workflow_id
  AND elementId(related) <> elementId(start)
RETURN DISTINCT related,
       labels(related) as labels,
       length(path) as distance,
       [rel in relationships(path) | type(rel)] as relationship_chain,
       elementId(related) as node_id,
       [rel in relationships(path) | properties(rel)] as relationship_properties
ORDER BY distance
LIMIT $max_nodes
"""

# Cypher query for fetching entity content by canonical_entity_id (fallback)
ENTITY_CONTENT_QUERY = """
MATCH (ce:CanonicalEntity)
WHERE ce.id = $canonical_entity_id
  AND ce.workflow_id = $workflow_id
RETURN ce.entity_type as entity_type,
       ce.attributes as attributes,
       ce.source_text as source_text
"""

# Log levels for different stages
LOG_STAGES = [
    "query_understanding",
    "vector_retrieval",
    "graph_expansion",
    "context_assembly",
    "response_generation",
]

# Metrics to track
TRACKED_METRICS = [
    "latency_ms",
    "vector_results_count",
    "graph_results_count",
    "merged_results_count",
    "context_tokens",
    "llm_tokens",
]


ERROR_MESSAGES = {
    "no_graph_data": "No graph data available for this workflow. Falling back to vector-only retrieval.",
    "node_mapping_failed": "Failed to map vector results to graph nodes. Continuing with vector results only.",
    "graph_traversal_failed": "Graph traversal failed. Continuing with vector results only.",
    "context_assembly_failed": "Failed to assemble context. Please try again.",
    "llm_generation_failed": "Failed to generate response. Please try again.",
    "workflow_not_found": "Workflow not found or access denied.",
    "no_results": "No relevant information found for your query.",
}


# Intent classification confidence threshold
MIN_INTENT_CONFIDENCE = 0.6

# Minimum number of vector results to proceed
MIN_VECTOR_RESULTS = 1

# Maximum query length
MAX_QUERY_LENGTH = 1000

# Maximum expanded queries
MAX_EXPANDED_QUERIES = 5

# Section types (for validation)
VALID_SECTION_TYPES = [
    "coverages",
    "exclusions",
    "conditions",
    "endorsements",
    "declarations",
    "schedule",
    "locations",
    "claims",
    "loss_run",
    "policy_info",
    "insured_info",
    "additional_insureds",
    "limits_deductibles",
    "forms",
    "definitions",
    "evidence",
]

# Entity types (for validation)
VALID_ENTITY_TYPES = [
    "coverage",
    "exclusion",
    "condition",
    "endorsement",
    "policy",
    "organization",
    "location",
    "claim",
    "definition",
    "vehicle",
    "driver",
]
