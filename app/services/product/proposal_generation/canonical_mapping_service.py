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
        return label.title()

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
