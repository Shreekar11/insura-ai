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
    MONTH_NAMES,
    CURRENCY_SYMBOL_TO_ISO,
    CURRENCY_NAME_TO_ISO,
    NUMBER_WORDS,
    CURRENCY_PATTERNS
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
    CURRENCY_SYMBOL_TO_ISO = CURRENCY_SYMBOL_TO_ISO
    CURRENCY_NAME_TO_ISO = CURRENCY_NAME_TO_ISO
    NUMBER_WORDS = NUMBER_WORDS
    CURRENCY_PATTERNS = CURRENCY_PATTERNS
    
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
    
    def parse_spelled_out_number(self, text: str) -> Optional[float]:
        """Parse spelled-out numbers to numeric values.
        
        Handles:
        - Basic numbers: "fifty" → 50
        - Compound numbers: "twenty five" → 25
        - With multipliers: "five thousand" → 5000, "two lakh" → 200000
        
        Args:
            text: Text containing spelled-out number
            
        Returns:
            float: Numeric value or None if parsing fails
            
        Example:
            >>> normalizer.parse_spelled_out_number("fifty")
            50.0
            >>> normalizer.parse_spelled_out_number("two lakh")
            200000.0
        """
        if not text:
            return None
        
        text = text.lower().strip()
        words = text.split()
        
        total = 0
        current = 0
        
        for word in words:
            if word in self.NUMBER_WORDS:
                value = self.NUMBER_WORDS[word]
                
                if value >= 100:
                    if current == 0:
                        current = 1
                    current *= value
                    if value >= 1000:
                        total += current
                        current = 0
                else:
                    current += value
        
        total += current
        return float(total) if total > 0 else None
    
    def clean_numeric_value(self, value_str: str, locale: str = 'en_US') -> Optional[float]:
        """Clean and parse numeric value handling different locale formats.
        
        Handles:
        - US format: 1,000.00 (comma as thousands, period as decimal)
        - EU format: 1.000,00 (period as thousands, comma as decimal)
        - Indian format: 1,20,000 (Indian numbering system)
        
        Args:
            value_str: Numeric string to clean
            locale: Locale hint ('en_US', 'en_IN', 'de_DE', etc.)
            
        Returns:
            float: Cleaned numeric value or None if parsing fails
        """
        if not value_str:
            return None
        
        value_str = value_str.strip()
        
        # Detect format based on patterns
        # European format: has period as thousands separator and comma as decimal
        if re.search(r'\d\.\d{3}', value_str) and ',' in value_str:
            # European: 1.000,00 → 1000.00
            value_str = value_str.replace('.', '').replace(',', '.')
        # Indian format: 1,20,000
        elif re.search(r'\d,\d{2},\d{3}', value_str):
            # Indian: 1,20,000 → 120000
            value_str = value_str.replace(',', '')
        # US format: 1,000.00
        else:
            # US: remove commas
            value_str = value_str.replace(',', '')
        
        try:
            return float(value_str)
        except ValueError:
            LOGGER.debug(f"Failed to parse numeric value: {value_str}")
            return None
    
    def normalize_currency(self, amount_str: str) -> Optional[Dict[str, Any]]:
        """Normalize currency amount to structured format with ISO 4217 code.
        
        Handles:
        - Symbol-based: $100, €50.50, £20, ₹1,20,000
        - ISO code: USD 100, EUR 50.50, GBP 20
        - Spelled-out: "fifty dollars", "two lakh rupees"
        - Various locales: 1,000.00 (US) vs 1.000,00 (EU)
        
        Args:
            amount_str: Amount string to normalize
            
        Returns:
            dict: {"amount": float, "currency": str} or None if parsing fails
            
        Example:
            >>> normalizer.normalize_currency("$1,200.50")
            {"amount": 1200.50, "currency": "USD"}
            >>> normalizer.normalize_currency("fifty pounds")
            {"amount": 50.0, "currency": "GBP"}
        """
        if not amount_str:
            return None
        
        amount_str = amount_str.strip()
        
        # Try spelled-out currency first
        lower_text = amount_str.lower()
        for currency_name, iso_code in self.CURRENCY_NAME_TO_ISO.items():
            if currency_name in lower_text:
                # Extract the number part
                number_part = lower_text.replace(currency_name, '').strip()
                amount = self.parse_spelled_out_number(number_part)
                if amount:
                    return {"amount": amount, "currency": iso_code}
        
        # Try pattern matching
        for pattern, pattern_type in self.CURRENCY_PATTERNS:
            match = re.search(pattern, amount_str)
            if match:
                try:
                    if pattern_type == 'iso_code':
                        # ISO code before amount: USD 100
                        iso_code = match.group(1)
                        amount_value = self.clean_numeric_value(match.group(2))
                        if amount_value and iso_code in self.CURRENCY_SYMBOL_TO_ISO.values():
                            return {"amount": amount_value, "currency": iso_code}
                    
                    elif pattern_type == 'iso_code_after':
                        # Amount before ISO code: 100 USD
                        amount_value = self.clean_numeric_value(match.group(1))
                        iso_code = match.group(2)
                        if amount_value and iso_code in self.CURRENCY_SYMBOL_TO_ISO.values():
                            return {"amount": amount_value, "currency": iso_code}
                    
                    elif pattern_type == 'symbol_before':
                        # Symbol before amount: $100
                        symbol = match.group(1)
                        amount_value = self.clean_numeric_value(match.group(2))
                        iso_code = self.CURRENCY_SYMBOL_TO_ISO.get(symbol)
                        if amount_value and iso_code:
                            return {"amount": amount_value, "currency": iso_code}
                    
                    elif pattern_type == 'indian':
                        # Indian format: Rs. 1,20,000/-
                        amount_value = self.clean_numeric_value(match.group(1), locale='en_IN')
                        if amount_value:
                            return {"amount": amount_value, "currency": "INR"}
                    
                    elif pattern_type == 'european':
                        # European format: 1.000,00 EUR
                        amount_value = self.clean_numeric_value(match.group(1), locale='de_DE')
                        iso_code = match.group(2)
                        if amount_value and iso_code in self.CURRENCY_SYMBOL_TO_ISO.values():
                            return {"amount": amount_value, "currency": iso_code}
                
                except (ValueError, IndexError) as e:
                    LOGGER.debug(f"Failed to parse currency: {amount_str}", extra={"error": str(e)})
                    continue
        
        LOGGER.debug(f"Could not normalize currency: {amount_str}")
        return None
    
    def normalize_amount(self, amount_str: str) -> Optional[Dict[str, Any]]:
        """Normalize monetary amount with currency code (BREAKING CHANGE).
        
        This method now returns structured currency data with ISO 4217 codes.
        
        Handles various currency formats:
        - Symbol-based: $1,200.50, ₹1,20,000, €50.50
        - ISO code: USD 100, EUR 50.50, GBP 20
        - Indian format: Rs. 12,500/-
        - Spelled-out: "fifty dollars", "two lakh rupees"
        
        Args:
            amount_str: Amount string to normalize
            
        Returns:
            dict: {"amount": float, "currency": str} or None if parsing fails
            
        Example:
            >>> normalizer.normalize_amount("$1,200.50")
            {"amount": 1200.50, "currency": "USD"}
            >>> normalizer.normalize_amount("Rs. 12,500/-")
            {"amount": 12500.0, "currency": "INR"}
        """
        return self.normalize_currency(amount_str)
    
    
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
        
        
        # Extract and normalize amounts with currency codes
        processed_positions = set()  # Track processed positions to avoid duplicates
        
        for pattern, pattern_type in self.CURRENCY_PATTERNS:
            for match in re.finditer(pattern, text):
                amount_str = match.group(0)
                start_pos = match.start()
                
                # Skip if we've already processed this position
                if start_pos in processed_positions:
                    continue
                
                normalized_currency = self.normalize_currency(amount_str)
                if normalized_currency:
                    extracted_fields["amounts"].append({
                        "original": amount_str,
                        "normalized": normalized_currency
                    })
                    
                    # Replace in text with standardized format: "1500.00 INR"
                    standardized_format = f"{normalized_currency['amount']:.2f} {normalized_currency['currency']}"
                    normalized_text = normalized_text.replace(amount_str, standardized_format, 1)
                    processed_positions.add(start_pos)
        
        
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
