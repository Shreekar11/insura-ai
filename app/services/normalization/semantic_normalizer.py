"""Semantic normalizer for deterministic field normalization.

This service handles rule-based normalization of structured fields that require
consistent formatting: dates, monetary amounts, policy/claim numbers, and emails.
"""

import re
from typing import Optional, Dict, Any

from app.utils.logging import get_logger
from app.services.normalization.constants import (
    INDIAN_CURRENCY_PATTERN,
    INTL_CURRENCY_PATTERN,
    AMOUNT_PATTERN,
    DATE_PATTERNS,
    MONTH_NAMES
)

LOGGER = get_logger(__name__)


class SemanticNormalizer:
    """Semantic normalizer for insurance document fields.
    
    This service performs deterministic normalization of structured fields:
    - Dates → YYYY-MM-DD format
    - Monetary amounts → numeric values (remove currency symbols, commas)
    - Policy/Claim numbers → uppercase, no spaces
    - Emails → lowercase, validated format
    
    Unlike LLM normalization, these operations are deterministic and rule-based.
    """

    # Assign imported constants to class attributes
    INDIAN_CURRENCY_PATTERN = INDIAN_CURRENCY_PATTERN
    INTL_CURRENCY_PATTERN = INTL_CURRENCY_PATTERN
    AMOUNT_PATTERN = AMOUNT_PATTERN
    DATE_PATTERNS = DATE_PATTERNS
    MONTH_NAMES = MONTH_NAMES
    
    def __init__(self):
        """Initialize semantic normalizer."""
        LOGGER.info("Initialized semantic normalizer")
    
    def normalize_date(self, date_str: str) -> Optional[str]:
        """Normalize date to YYYY-MM-DD format.
        
        Handles various date formats:
        - 12/12/2023, 12-12-2023
        - 12/12/23
        - 12th Dec 2023, 12 December 2023
        - Dec 12, 2023
        
        Args:
            date_str: Date string to normalize
            
        Returns:
            str: Date in YYYY-MM-DD format, or None if parsing fails
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Try each date pattern
        for pattern, format_type in self.DATE_PATTERNS:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                try:
                    if format_type == 'mdy':
                        month, day, year = match.groups()
                        return f"{year}-{int(month):02d}-{int(day):02d}"
                    
                    elif format_type == 'mdy_short':
                        month, day, year = match.groups()
                        year = f"20{year}" if int(year) < 50 else f"19{year}"
                        return f"{year}-{int(month):02d}-{int(day):02d}"
                    
                    elif format_type == 'dmy_text':
                        day, month_name, year = match.groups()
                        month = self.MONTH_NAMES.get(month_name.lower())
                        if month:
                            return f"{year}-{month:02d}-{int(day):02d}"
                    
                    elif format_type == 'mdy_text':
                        month_name, day, year = match.groups()
                        month = self.MONTH_NAMES.get(month_name.lower())
                        if month:
                            return f"{year}-{month:02d}-{int(day):02d}"
                
                except (ValueError, AttributeError) as e:
                    LOGGER.debug(f"Failed to parse date: {date_str}", extra={"error": str(e)})
                    continue
        
        LOGGER.debug(f"Could not normalize date: {date_str}")
        return None
    
    def normalize_amount(self, amount_str: str) -> Optional[float]:
        """Normalize monetary amount to numeric value.
        
        Handles various currency formats:
        - ₹1,20,000
        - Rs. 12,500/-
        - USD $500.00
        - 25,00,000.00
        
        Args:
            amount_str: Amount string to normalize
            
        Returns:
            float: Numeric amount, or None if parsing fails
        """
        if not amount_str:
            return None
        
        amount_str = amount_str.strip()
        
        # Try Indian currency pattern
        match = re.search(self.INDIAN_CURRENCY_PATTERN, amount_str)
        if match:
            amount = match.group(1).replace(',', '')
            try:
                return float(amount)
            except ValueError:
                pass
        
        # Try international currency pattern
        match = re.search(self.INTL_CURRENCY_PATTERN, amount_str)
        if match:
            amount = match.group(1).replace(',', '')
            try:
                return float(amount)
            except ValueError:
                pass
        
        # Try generic amount pattern
        match = re.search(self.AMOUNT_PATTERN, amount_str)
        if match:
            amount = match.group(1).replace(',', '')
            try:
                return float(amount)
            except ValueError:
                pass
        
        LOGGER.debug(f"Could not normalize amount: {amount_str}")
        return None
    
    
    def normalize_policy_number(self, policy_number: str) -> Optional[str]:
        """Normalize policy number.
        
        - Remove spaces
        - Convert to uppercase
        - Remove trailing special characters
        
        Args:
            policy_number: Policy number to normalize
            
        Returns:
            str: Normalized policy number
            
        Example:
            >>> normalizer = SemanticNormalizer()
            >>> normalizer.normalize_policy_number("pol 12345-a")
            'POL12345-A'
        """
        if not policy_number:
            return None
        
        # Remove spaces
        normalized = policy_number.replace(' ', '')
        
        # Convert to uppercase
        normalized = normalized.upper()
        
        # Remove trailing special characters (except hyphens within)
        normalized = re.sub(r'[^\w-]', '', normalized)
        
        return normalized if normalized else None
    
    
    def normalize_email(self, email: str) -> Optional[str]:
        """Normalize email address.
        
        - Convert to lowercase
        - Remove spaces
        
        Args:
            email: Email to normalize
            
        Returns:
            str: Normalized email
        """
        if not email:
            return None
        
        # Remove spaces and convert to lowercase
        normalized = email.replace(' ', '').lower()
        
        # Basic validation
        if '@' in normalized and '.' in normalized.split('@')[1]:
            return normalized
        
        return None
    
    def normalize_text_with_fields(self, text: str) -> Dict[str, Any]:
        """Normalize text and extract structured fields.
        
        This method scans the text for common insurance fields and
        normalizes them in place while also extracting them.
        
        Args:
            text: Text to normalize
            
        Returns:
            dict: Dictionary with normalized_text and extracted_fields
        """
        if not text:
            return {"normalized_text": "", "extracted_fields": {}}
        
        normalized_text = text
        extracted_fields = {
            "dates": [],
            "amounts": [],
            "emails": [],
        }
        
        # Extract and normalize dates
        for pattern, _ in self.DATE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                date_str = match.group(0)
                normalized_date = self.normalize_date(date_str)
                if normalized_date:
                    extracted_fields["dates"].append({
                        "original": date_str,
                        "normalized": normalized_date
                    })
                    # Replace in text
                    normalized_text = normalized_text.replace(date_str, normalized_date)
        
        # Extract and normalize amounts
        for match in re.finditer(self.INDIAN_CURRENCY_PATTERN, text):
            amount_str = match.group(0)
            normalized_amount = self.normalize_amount(amount_str)
            if normalized_amount is not None:
                extracted_fields["amounts"].append({
                    "original": amount_str,
                    "normalized": normalized_amount
                })
        
        # Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, text):
            email_str = match.group(0)
            normalized_email = self.normalize_email(email_str)
            if normalized_email:
                extracted_fields["emails"].append({
                    "original": email_str,
                    "normalized": normalized_email
                })
                # Replace in text
                normalized_text = normalized_text.replace(email_str, normalized_email)
        
        LOGGER.info(
            "Semantic normalization completed",
            extra={
                "dates_found": len(extracted_fields["dates"]),
                "amounts_found": len(extracted_fields["amounts"]),
                "emails_found": len(extracted_fields["emails"]),
            }
        )
        
        return {
            "normalized_text": normalized_text,
            "extracted_fields": extracted_fields
        }
