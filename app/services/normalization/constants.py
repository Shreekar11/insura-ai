# ISO 4217 Currency Code Mappings
CURRENCY_SYMBOL_TO_ISO = {
    '$': 'USD',
    '€': 'EUR',
    '£': 'GBP',
    '¥': 'JPY',
    '₹': 'INR',
    'Rs': 'INR',
    'Rs.': 'INR',
    '₨': 'INR',
    'CHF': 'CHF',
    'C$': 'CAD',
    'A$': 'AUD',
}

CURRENCY_NAME_TO_ISO = {
    'dollar': 'USD', 'dollars': 'USD',
    'euro': 'EUR', 'euros': 'EUR',
    'pound': 'GBP', 'pounds': 'GBP',
    'rupee': 'INR', 'rupees': 'INR',
    'yen': 'JPY',
    'franc': 'CHF', 'francs': 'CHF',
}

# Spelled-out number words
NUMBER_WORDS = {
    # Basic numbers
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
    'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
    'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
    'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
    # Multipliers
    'hundred': 100,
    'thousand': 1000,
    'million': 1000000,
    'billion': 1000000000,
    # Indian numbering system
    'lakh': 100000,
    'lac': 100000,
    'crore': 10000000,
}

# Enhanced currency patterns (order matters - most specific first)
CURRENCY_PATTERNS = [
    # Indian format FIRST (most specific): Rs. 1,20,000/-, ₹25,00,000, Rs. 12,500/-
    (r'(?:Rs\.?|₹|₨)\s*([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{2})?)\s*(?:/-)?', 'indian'),
    # ISO code with amount: USD 100, EUR 50.50, GBP 20
    (r'\b([A-Z]{3})\s+([0-9]{1,3}(?:[,\s][0-9]{3})*(?:[.,][0-9]{2})?)\b', 'iso_code'),
    # Amount with ISO code: 100 USD, 50.50 EUR
    (r'\b([0-9]{1,3}(?:[,\s][0-9]{3})*(?:[.,][0-9]{2})?)\s+([A-Z]{3})\b', 'iso_code_after'),
    # Symbol before amount: $100, €50.50, £20
    (r'([\$€£¥])\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)', 'symbol_before'),
    # European format: 1.000,00 EUR (period as thousands, comma as decimal)
    (r'\b([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)\s*([A-Z]{3})\b', 'european'),
]

# Legacy patterns (kept for backward compatibility)
INDIAN_CURRENCY_PATTERN = r'(?:Rs\.?|₹)\s*(\d+(?:,\d+)*(?:\.\d{2})?)\s*(?:/-)?'
INTL_CURRENCY_PATTERN = r'(?:USD|EUR|GBP)?\s*[$€£]\s*(\d+(?:,\d+)*(?:\.\d{2})?)'

# Generic amount pattern
AMOUNT_PATTERN = r'(\d+(?:,\d+)*(?:\.\d{2})?)'

# Date patterns
DATE_PATTERNS = [
    (r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', 'mdy'),
    (r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b', 'mdy_short'),
    (r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)[,\s]+(\d{4})\b', 'dmy_text'),
    (r'\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?[,\s]+(\d{4})\b', 'mdy_text'),
]

# Month name mappings
MONTH_NAMES = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}
