"""Service for mapping carrier-specific terms to canonical taxonomy."""

from typing import Dict, List, Optional
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class CanonicalMappingService:
    """Provides mapping for carrier-specific labels to a canonical taxonomy.
    
    This ensures that "GL", "Gen Liab", and "Commercial General Liability" 
    all map to the same canonical "General Liability" concept for comparison.
    """
    
    # Coverage Mapping: Carrier-specific label -> Canonical label
    COVERAGE_MAP: Dict[str, str] = {
        # General Liability
        "gl": "General Liability",
        "gen liab": "General Liability",
        "commercial general liability": "General Liability",
        "cgl": "General Liability",
        
        # Property
        "property": "Commercial Property",
        "comm prop": "Commercial Property",
        "building": "Commercial Property",
        "bpp": "Business Personal Property",
        
        # Workers Comp
        "wc": "Workers Compensation",
        "workers comp": "Workers Compensation",
        "workers' compensation": "Workers Compensation",
        
        # Umbrella/Excess
        "umb": "Umbrella Liability",
        "umbrella": "Umbrella Liability",
        "excess": "Excess Liability",
        "excess liab": "Excess Liability",
        
        # Cyber
        "cyber": "Cyber Liability",
        "privacy": "Cyber Liability",
        "network security": "Cyber Liability",
        
        # Auto
        "auto": "Commercial Auto",
        "comm auto": "Commercial Auto",
        "hired and non-owned auto": "Hired & Non-Owned Auto",
        "hnoa": "Hired & Non-Owned Auto",
    }
    
    # Carrier Mapping: Normalized Carrier Name -> Canonical Carrier Name
    CARRIER_MAP: Dict[str, str] = {
        "travelers": "Travelers",
        "the travelers": "Travelers",
        "hartford": "The Hartford",
        "the hartford": "The Hartford",
        "chubb": "Chubb",
        "liberty mutual": "Liberty Mutual",
        "nationwide": "Nationwide",
        "progressive": "Progressive",
        "state farm": "State Farm",
        "berkshire hathaway": "Berkshire Hathaway",
        "geico": "GEICO",
    }
    
    # Generic Mapping for Deductibles
    DEDUCTIBLE_MAP: Dict[str, str] = {
        "aop": "All Other Perils",
        "all other perils": "All Other Perils",
        "wind": "Wind/Hail",
        "hail": "Wind/Hail",
        "wind/hail": "Wind/Hail",
        "named storm": "Named Storm",
        "earthquake": "Earthquake",
        "eq": "Earthquake",
        "flood": "Flood",
    }

    @classmethod
    def canonicalize_coverage(cls, label: str) -> str:
        """Map a coverage label to its canonical name."""
        if not label:
            return "Unknown Coverage"
        
        normalized = label.lower().strip()
        # Exact match
        if normalized in cls.COVERAGE_MAP:
            return cls.COVERAGE_MAP[normalized]
        
        # Partial match heuristic
        for key, value in cls.COVERAGE_MAP.items():
            if key in normalized:
                return value
                
        # Return title-cased original if no match
        # Return title-cased original if no match
        return label.title()

    @classmethod
    def get_canonical_coverage_name(cls, label: str) -> str:
        """Alias for canonicalize_coverage."""
        return cls.canonicalize_coverage(label)

    @classmethod
    def get_canonical_deductible_name(cls, label: str) -> str:
        """Map a deductible label to its canonical name."""
        if not label:
            return "Unknown Deductible"
            
        normalized = label.lower().strip()
        if normalized in cls.DEDUCTIBLE_MAP:
            return cls.DEDUCTIBLE_MAP[normalized]
            
        for key, value in cls.DEDUCTIBLE_MAP.items():
            if key in normalized:
                return value
                
        return label.title()

    @classmethod
    def get_canonical_exclusion_name(cls, label: str) -> str:
        """Map an exclusion label to its canonical name."""
        # For now, just title case, can add specific mappings later
        return label.title() if label else "Unknown Exclusion"

    @classmethod
    def get_canonical_endorsement_name(cls, label: str) -> str:
        """Map an endorsement label to its canonical name."""
        # For now, just title case, can add specific mappings later
        return label.title() if label else "Unknown Endorsement"

    @classmethod
    def get_canonical_name(cls, section_type: str, label: str) -> str:
        """Get canonical name based on section type."""
        if section_type == "coverages":
            return cls.get_canonical_coverage_name(label)
        elif section_type == "deductibles":
            return cls.get_canonical_deductible_name(label)
        elif section_type == "exclusions":
            return cls.get_canonical_exclusion_name(label)
        elif section_type == "endorsements":
            return cls.get_canonical_endorsement_name(label)
        else:
            return label.title() if label else "Unknown"

    @classmethod
    def canonicalize_carrier(cls, name: str) -> str:
        """Map a carrier name to its canonical name."""
        if not name:
            return "Unknown Carrier"
            
        normalized = name.lower().strip()
        for key, value in cls.CARRIER_MAP.items():
            if key in normalized:
                return value
                
        return name.title()
