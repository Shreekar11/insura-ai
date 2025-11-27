"""Deterministic parser for insurance entities.

This module provides regex-based parsing to backstop LLM entity extraction.
It uses pattern matching to extract critical entities (policy numbers, insured names,
dates, carriers) when LLM extraction misses them.
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class InsuranceEntityParser:
    """Deterministic regex-based parser for insurance entities.
    
    This parser uses pattern matching to extract entities that may be missed
    by LLM extraction. It provides a backstop layer to ensure critical entities
    are always captured.
    
    Attributes:
        policy_patterns: Regex patterns for policy numbers
        insured_patterns: Regex patterns for insured names
        date_patterns: Regex patterns for dates
        carrier_patterns: Known carrier names
    """
    
    # Policy number patterns
    POLICY_PATTERNS = [
        # POL-123-456, POL123456, POLICY-ABC-123
        r'(?:POL|POLICY)[-\s]?(?:NO\.?|NUMBER)?[-\s]?([A-Z0-9-]+)',
        # Policy No: ABC123, Policy Number: 12345
        r'Policy\s+(?:No\.?|Number):\s*([A-Z0-9-]+)',
        # Standalone alphanumeric codes (conservative)
        r'\b([A-Z]{2,4}[-/]?\d{4,10})\b',
    ]
    
    # Insured name patterns
    INSURED_PATTERNS = [
        # Insured: ABC Company, Named Insured: John Doe
        r'(?:INSURED|NAMED INSURED):\s*([A-Za-z\s,\.&\'-]+?)(?:\n|$|;)',
        # Insured Name: ABC Corp
        r'Insured\s+Name:\s*([A-Za-z\s,\.&\'-]+?)(?:\n|$|;)',
        # Name of Insured: XYZ LLC
        r'Name\s+of\s+Insured:\s*([A-Za-z\s,\.&\'-]+?)(?:\n|$|;)',
    ]
    
    # Date patterns
    DATE_PATTERNS = [
        # ISO format: 2024-01-15
        (r'\b(\d{4}-\d{2}-\d{2})\b', '%Y-%m-%d'),
        # US format: 01/15/2024, 1/15/2024
        (r'\b(\d{1,2}/\d{1,2}/\d{4})\b', '%m/%d/%Y'),
        # International: 15-01-2024, 15.01.2024
        (r'\b(\d{1,2}[-\.]\d{1,2}[-\.]\d{4})\b', '%d-%m-%Y'),
        # Month name: January 15, 2024
        (r'\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})\b', '%B %d, %Y'),
    ]
    
    # Common carrier names (can be extended from database/config)
    KNOWN_CARRIERS = [
        "SBI General Insurance",
        "HDFC ERGO",
        "ICICI Lombard",
        "Bajaj Allianz",
        "Reliance General Insurance",
        "Tata AIG",
        "United India Insurance",
        "National Insurance",
        "New India Assurance",
        "Oriental Insurance",
        # Add more as needed
    ]
    
    def __init__(self, additional_carriers: Optional[List[str]] = None):
        """Initialize parser.
        
        Args:
            additional_carriers: Additional carrier names to recognize
        """
        self.policy_patterns = [re.compile(p, re.IGNORECASE) for p in self.POLICY_PATTERNS]
        self.insured_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.INSURED_PATTERNS]
        
        # Build carrier list
        self.carriers = self.KNOWN_CARRIERS.copy()
        if additional_carriers:
            self.carriers.extend(additional_carriers)
        
        LOGGER.info(
            "Initialized InsuranceEntityParser",
            extra={"known_carriers": len(self.carriers)}
        )
    
    def parse_policy_numbers(self, text: str) -> List[Dict[str, Any]]:
        """Parse policy numbers from text.
        
        Args:
            text: Text to parse
            
        Returns:
            List of policy number entities with confidence scores
        """
        entities = []
        seen_values = set()
        
        for pattern in self.policy_patterns:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                
                # Skip if already found
                if value in seen_values:
                    continue
                
                # Validate: should have both letters and numbers
                if not (any(c.isalpha() for c in value) and any(c.isdigit() for c in value)):
                    continue
                
                # Confidence based on pattern strength
                confidence = self._calculate_policy_confidence(match.group(0), value)
                
                entities.append({
                    "entity_type": "POLICY_NUMBER",
                    "raw_value": match.group(0).strip(),
                    "normalized_value": value.upper().replace(" ", ""),
                    "confidence": confidence,
                    "span_start": match.start(),
                    "span_end": match.end(),
                    "source": "deterministic_parser"
                })
                
                seen_values.add(value)
        
        LOGGER.debug(
            f"Parsed {len(entities)} policy numbers",
            extra={"count": len(entities)}
        )
        
        return entities
    
    def parse_insured_names(self, text: str) -> List[Dict[str, Any]]:
        """Parse insured names from text.
        
        Args:
            text: Text to parse
            
        Returns:
            List of insured name entities with confidence scores
        """
        entities = []
        seen_values = set()
        
        for pattern in self.insured_patterns:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                
                # Clean up value
                value = re.sub(r'\s+', ' ', value)  # Normalize whitespace
                value = value.rstrip('.,;')  # Remove trailing punctuation
                
                # Skip if already found or too short
                if value in seen_values or len(value) < 3:
                    continue
                
                # Confidence based on pattern strength
                confidence = self._calculate_insured_confidence(match.group(0), value)
                
                entities.append({
                    "entity_type": "INSURED_NAME",
                    "raw_value": match.group(0).strip(),
                    "normalized_value": value,
                    "confidence": confidence,
                    "span_start": match.start(),
                    "span_end": match.end(),
                    "source": "deterministic_parser"
                })
                
                seen_values.add(value)
        
        LOGGER.debug(
            f"Parsed {len(entities)} insured names",
            extra={"count": len(entities)}
        )
        
        return entities
    
    def parse_dates(self, text: str, date_type: str = "EFFECTIVE_DATE") -> List[Dict[str, Any]]:
        """Parse dates from text.
        
        Args:
            text: Text to parse
            date_type: Type of date (EFFECTIVE_DATE or EXPIRATION_DATE)
            
        Returns:
            List of date entities with confidence scores
        """
        entities = []
        seen_values = set()
        
        for pattern_str, date_format in self.DATE_PATTERNS:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            
            for match in pattern.finditer(text):
                date_str = match.group(1).strip()
                
                # Try to parse date
                try:
                    parsed_date = datetime.strptime(date_str, date_format)
                    normalized_value = parsed_date.strftime('%Y-%m-%d')
                    
                    # Skip if already found
                    if normalized_value in seen_values:
                        continue
                    
                    # Confidence based on format
                    confidence = 0.8 if date_format == '%Y-%m-%d' else 0.7
                    
                    entities.append({
                        "entity_type": date_type,
                        "raw_value": date_str,
                        "normalized_value": normalized_value,
                        "confidence": confidence,
                        "span_start": match.start(),
                        "span_end": match.end(),
                        "source": "deterministic_parser"
                    })
                    
                    seen_values.add(normalized_value)
                    
                except ValueError:
                    # Invalid date, skip
                    continue
        
        LOGGER.debug(
            f"Parsed {len(entities)} {date_type} dates",
            extra={"count": len(entities), "date_type": date_type}
        )
        
        return entities
    
    def parse_carriers(self, text: str) -> List[Dict[str, Any]]:
        """Parse carrier names from text.
        
        Args:
            text: Text to parse
            
        Returns:
            List of carrier entities with confidence scores
        """
        entities = []
        seen_values = set()
        
        for carrier in self.carriers:
            # Case-insensitive search
            pattern = re.compile(re.escape(carrier), re.IGNORECASE)
            
            for match in pattern.finditer(text):
                value = match.group(0)
                
                # Skip if already found
                if value.lower() in seen_values:
                    continue
                
                entities.append({
                    "entity_type": "CARRIER",
                    "raw_value": value,
                    "normalized_value": carrier,  # Use canonical name
                    "confidence": 0.9,  # High confidence for known carriers
                    "span_start": match.start(),
                    "span_end": match.end(),
                    "source": "deterministic_parser"
                })
                
                seen_values.add(value.lower())
        
        LOGGER.debug(
            f"Parsed {len(entities)} carriers",
            extra={"count": len(entities)}
        )
        
        return entities
    
    def parse_all(self, text: str) -> List[Dict[str, Any]]:
        """Parse all entity types from text.
        
        Args:
            text: Text to parse
            
        Returns:
            List of all parsed entities
        """
        entities = []
        
        entities.extend(self.parse_policy_numbers(text))
        entities.extend(self.parse_insured_names(text))
        entities.extend(self.parse_dates(text, "EFFECTIVE_DATE"))
        entities.extend(self.parse_dates(text, "EXPIRATION_DATE"))
        entities.extend(self.parse_carriers(text))
        
        LOGGER.info(
            f"Parsed {len(entities)} total entities",
            extra={
                "total": len(entities),
                "by_type": self._count_by_type(entities)
            }
        )
        
        return entities
    
    def _calculate_policy_confidence(self, full_match: str, value: str) -> float:
        """Calculate confidence score for policy number.
        
        Args:
            full_match: Full matched string
            value: Extracted value
            
        Returns:
            Confidence score (0.0-1.0)
        """
        # Higher confidence if explicitly labeled
        if re.search(r'policy\s+(?:no|number)', full_match, re.IGNORECASE):
            return 0.9
        
        # Medium confidence for POL prefix
        if value.upper().startswith('POL'):
            return 0.8
        
        # Lower confidence for standalone codes
        return 0.6
    
    def _calculate_insured_confidence(self, full_match: str, value: str) -> float:
        """Calculate confidence score for insured name.
        
        Args:
            full_match: Full matched string
            value: Extracted value
            
        Returns:
            Confidence score (0.0-1.0)
        """
        # Higher confidence if explicitly labeled
        if re.search(r'named\s+insured', full_match, re.IGNORECASE):
            return 0.9
        
        if re.search(r'insured\s+name', full_match, re.IGNORECASE):
            return 0.85
        
        # Medium confidence for "Insured:" label
        return 0.8
    
    def _count_by_type(self, entities: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count entities by type.
        
        Args:
            entities: List of entities
            
        Returns:
            Dictionary mapping entity type to count
        """
        counts = {}
        for entity in entities:
            entity_type = entity.get("entity_type", "UNKNOWN")
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return counts
