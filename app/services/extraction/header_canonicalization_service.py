"""Header canonicalization service for mapping raw headers to insurance domain fields.

This service maps raw table headers to canonical insurance domain fields
using rules-based matching (not LLM), per Phase 5 requirements.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

from app.services.extraction.table_extraction_service import TableStructure, ColumnMapping
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Mapping rules: raw header patterns -> canonical field names
HEADER_MAPPINGS = {
    # SOV fields - Location identifiers
    "location": [
        "location", "loc", "loc #", "loc#", "location number", "location id",
        "loc no", "loc no.", "location no", "location no."
    ],
    "building_number": [
        "bldg #", "bldg#", "bldg", "building #", "building number",
        "bldg no", "bldg no.", "building no", "building no.", "# bldgs"
    ],
    "address": [
        "address", "location address", "property address", "street",
        "description"  # Often "description" column contains address in SOVs
    ],
    
    # SOV fields - Values
    "building_value": [
        "building", "bldg", "building value", "building limit", "bldg value",
        "building coverage", "bldg coverage"
    ],
    "contents_value": [
        "contents", "contents value", "contents limit", "personal property",
        "business personal property", "bpp", "bpp value"
    ],
    "tenant_improvements": [
        "tenant improvements", "tenant improvements and betterments",
        "ti&b", "ti & b", "betterments", "improvements"
    ],
    "business_income": [
        "bi", "business income", "business interruption", "loss of income",
        "business income and extra expense", "bi/ee", "extra expense"
    ],
    "additional_property": [
        "additional property", "additional property coverage",
        "additional coverage", "other coverage", "apc"
    ],
    "tiv": [
        "tiv", "total insured value", "total value", "total", "insured value",
        "total values", "total stated values", "total limit"
    ],
    
    # SOV fields - Property characteristics
    "description": [
        "description", "desc", "property description", "building description",
        "property type", "building type"
    ],
    "construction_type": [
        "construction", "construction type", "construction class", "class",
        "const", "const type"
    ],
    "occupancy": [
        "occupancy", "occupancy type", "use", "occupancy class"
    ],
    "year_built": [
        "year built", "year", "built", "construction year", "yr built"
    ],
    "square_footage": [
        "square feet", "sq ft", "sqft", "area", "size", "square footage"
    ],
    "distance_to_coast": [
        "distance to coast", "coast distance", "distance to coast (mi.)",
        "dist to coast", "coastal distance"
    ],
    "flood_zone": [
        "flood zone", "flood", "fema zone", "fema flood zone", "zone"
    ],
    
    # Loss Run fields
    "claim_number": [
        "claim", "claim number", "claim #", "claim#", "claim id",
        "claim no", "claim no."
    ],
    "policy_number": [
        "policy", "policy number", "policy #", "policy#", "policy id",
        "policy no", "policy no."
    ],
    "insured_name": [
        "insured", "insured name", "named insured", "client", "claimant"
    ],
    "loss_date": [
        "loss date", "date of loss", "loss", "dol", "date loss",
        "date of occurrence", "occurrence date"
    ],
    "report_date": [
        "report date", "reported", "date reported", "report",
        "notification date"
    ],
    "cause_of_loss": [
        "cause", "cause of loss", "loss cause", "peril", "type",
        "loss type", "peril type"
    ],
    "loss_description": [
        "loss description", "claim description", "description of loss"
    ],
    "incurred_amount": [
        "incurred", "incurred amount", "total incurred", "incurred $",
        "total incurred amount"
    ],
    "paid_amount": [
        "paid", "paid amount", "amount paid", "paid $", "total paid"
    ],
    "reserve_amount": [
        "reserve", "reserve amount", "reserves", "reserve $",
        "outstanding reserve", "outstanding"
    ],
    "status": [
        "status", "claim status", "state", "claim state"
    ],
}


class HeaderCanonicalizationService:
    """Service for mapping raw table headers to canonical insurance domain fields.
    
    Uses rules-based matching (not LLM) per Phase 5 requirements.
    """
    
    def __init__(self):
        """Initialize header canonicalization service."""
        LOGGER.info("Initialized HeaderCanonicalizationService")
    
    def canonicalize_headers(
        self,
        table: TableStructure,
        table_type: str
    ) -> List[ColumnMapping]:
        """Map raw headers to canonical field names.
        
        Args:
            table: TableStructure with headers
            table_type: Table type (property_sov, loss_run, etc.)
            
        Returns:
            List of ColumnMapping objects
        """
        mappings = []
        
        if not table.headers:
            return mappings
        
        # Filter mappings based on table type
        relevant_fields = self._get_relevant_fields_for_table_type(table_type)
        
        for idx, raw_header in enumerate(table.headers):
            canonical_field = self._match_header_to_field(raw_header, relevant_fields)
            
            mapping = ColumnMapping(
                index=idx,
                raw_header=raw_header,
                canonical_field=canonical_field,
                confidence=self._calculate_confidence(raw_header, canonical_field)
            )
            
            mappings.append(mapping)
        
        LOGGER.debug(
            f"Canonicalized {len(mappings)} headers for {table_type} table",
            extra={
                "table_id": table.table_id,
                "mappings": [m.canonical_field for m in mappings]
            }
        )
        
        return mappings
    
    def _get_relevant_fields_for_table_type(self, table_type: str) -> List[str]:
        """Get relevant canonical fields for a table type.
        
        Args:
            table_type: Table type
            
        Returns:
            List of relevant canonical field names
        """
        if table_type == "property_sov":
            return [
                "location", "building_number", "address", "building_value", 
                "contents_value", "tenant_improvements", "business_income", 
                "additional_property", "tiv", "description", "construction_type",
                "occupancy", "year_built", "square_footage", "distance_to_coast",
                "flood_zone"
            ]
        elif table_type == "loss_run":
            return [
                "claim_number", "policy_number", "insured_name", "loss_date",
                "report_date", "cause_of_loss", "loss_description", "incurred_amount",
                "paid_amount", "reserve_amount", "status"
            ]
        else:
            # For other types, return all fields
            return list(HEADER_MAPPINGS.keys())
    
    def _match_header_to_field(
        self,
        raw_header: str,
        relevant_fields: List[str]
    ) -> str:
        """Match a raw header to a canonical field name.
        
        Args:
            raw_header: Raw header text (may be cleaned/reconstructed)
            relevant_fields: List of relevant canonical fields
            
        Returns:
            Canonical field name or "unknown_{index}" if no match
        """
        normalized_header = raw_header.lower().strip()
        
        # Clean up header: remove common prefixes/suffixes that get concatenated
        # Handle cases like "Loc #" or "loc#" even when concatenated
        cleaned_header = self._clean_header_for_matching(normalized_header)
        
        # Try exact match first
        for field, patterns in HEADER_MAPPINGS.items():
            if field not in relevant_fields:
                continue
            if cleaned_header in [p.lower() for p in patterns]:
                return field
        
        # Try partial match (substring)
        for field, patterns in HEADER_MAPPINGS.items():
            if field not in relevant_fields:
                continue
            for pattern in patterns:
                pattern_lower = pattern.lower()
                # Check if pattern is in header or header is in pattern
                if pattern_lower in cleaned_header or cleaned_header in pattern_lower:
                    return field
        
        # Try keyword matching (word-level)
        for field, patterns in HEADER_MAPPINGS.items():
            if field not in relevant_fields:
                continue
            for pattern in patterns:
                pattern_words = [w for w in pattern.lower().split() if len(w) > 2]
                header_words = cleaned_header.split()
                # Check if any significant word from pattern appears in header
                if any(word in cleaned_header for word in pattern_words):
                    return field
        
        # Try abbreviation matching (e.g., "loc" matches "location")
        for field, patterns in HEADER_MAPPINGS.items():
            if field not in relevant_fields:
                continue
            for pattern in patterns:
                # Extract abbreviations (first letters of words)
                pattern_abbrev = ''.join([w[0] for w in pattern.lower().split() if w])
                if len(pattern_abbrev) >= 2 and pattern_abbrev in cleaned_header:
                    return field
        
        # No match found
        return f"unknown_{cleaned_header.replace(' ', '_')[:30]}"
    
    def _clean_header_for_matching(self, header: str) -> str:
        """Clean header text for better matching.
        
        Removes common concatenation artifacts and extracts the relevant part.
        
        Args:
            header: Raw header text (may be concatenated like "Policy Title.Org Name.Column Name")
            
        Returns:
            Cleaned header text (just the column name part)
        """
        import re
        
        if not header:
            return ""
        
        # Remove common prefixes that get concatenated
        prefixes_to_remove = [
            r'^total\s+stated\s+values\s+under\s+policy[.\s]*',
            r'^.*association[.\s]*',
            r'^.*inc[.\s]*',
            r'^.*condominium[.\s]*',
            r'^\d{2}-\d+-\s*[A-Z]-\d+[.\s]*',  # Policy numbers like "01-7590121387- S-02"
            r'^.*harbor\s+cove[.\s]*',
        ]
        
        cleaned = header
        for prefix_pattern in prefixes_to_remove:
            cleaned = re.sub(prefix_pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Split on dots, periods, or multiple spaces/periods
        # Pattern like "Policy Title.Org Name.Column Name" or "Loc #..1"
        parts = re.split(r'[.\s]{2,}|\.(?=\w)', cleaned)
        
        if parts:
            # Filter out empty parts and very long parts (likely organization names)
            meaningful_parts = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # Skip very long parts (likely document titles or org names)
                if len(part) > 50:
                    continue
                # Skip parts that look like policy numbers
                if re.match(r'^\d{2}-\d+-\s*[A-Z]-\d+$', part):
                    continue
                meaningful_parts.append(part)
            
            if meaningful_parts:
                # Prefer shorter parts (more likely to be column names)
                # Column names are usually short: "Loc #", "Building", "Address"
                # vs long: "Total Stated Values Under Policy"
                cleaned = min(meaningful_parts, key=len)
            else:
                # If all parts were filtered, try to extract just the last segment
                # Handle patterns like "Loc #..1" -> "Loc #"
                last_segment = re.split(r'\.+', header)[-1]
                if last_segment and len(last_segment) < 50:
                    cleaned = last_segment.strip()
        
        # Clean up common suffixes
        cleaned = re.sub(r'\.+$', '', cleaned)  # Remove trailing dots
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
        
        return cleaned.strip()
    
    def _calculate_confidence(
        self,
        raw_header: str,
        canonical_field: str
    ) -> float:
        """Calculate confidence score for a header mapping.
        
        Args:
            raw_header: Raw header text
            canonical_field: Canonical field name
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if canonical_field.startswith("unknown_"):
            return 0.0
        
        normalized_header = raw_header.lower().strip()
        patterns = HEADER_MAPPINGS.get(canonical_field, [])
        
        # Exact match = high confidence
        if normalized_header in [p.lower() for p in patterns]:
            return 1.0
        
        # Partial match = medium confidence
        for pattern in patterns:
            if pattern.lower() in normalized_header or normalized_header in pattern.lower():
                return 0.8
        
        # Keyword match = lower confidence
        for pattern in patterns:
            pattern_words = pattern.lower().split()
            header_words = normalized_header.split()
            if any(word in header_words for word in pattern_words if len(word) > 3):
                return 0.6
        
        return 0.5

