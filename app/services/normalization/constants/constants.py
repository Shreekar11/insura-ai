# Currency patterns
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
