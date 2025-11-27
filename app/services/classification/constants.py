"""Classification constants and configuration.

This module defines document types, confidence thresholds, and other
constants used by the classification service.
"""

# Document types supported by the classification system
DOCUMENT_TYPES = [
    "policy",
    "claim",
    "submission",
    "quote",
    "proposal",
    "SOV",  # Schedule of Values
    "financials",
    "loss_run",
    "audit",
    "endorsement",
    "invoice",
    "correspondence",
]

# Confidence thresholds for classification decisions
ACCEPT_THRESHOLD = 0.75  # Auto-accept classification if confidence >= this
REVIEW_THRESHOLD = 0.50  # Trigger fallback/review if confidence < this

# Chunk weighting factors
DEFAULT_CHUNK_WEIGHT = 1.0
FIRST_PAGE_WEIGHT = 1.5  # First page typically has important metadata
DECLARATIONS_PAGE_WEIGHT = 2.0  # Declarations pages are highly indicative

# Keywords that indicate specific document types (for weighting)
KEYWORD_MULTIPLIERS = {
    "declarations page": 2.0,
    "policy number": 1.5,
    "claim number": 1.5,
    "loss date": 1.5,
    "schedule of values": 2.0,
    "total insured value": 1.8,
    "tiv": 1.8,
    "balance sheet": 1.8,
    "income statement": 1.8,
}

# Minimum confidence for any classification
MIN_CONFIDENCE = 0.1
