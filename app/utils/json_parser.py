import json
import re
from typing import Any, Dict, List, Union, Optional

from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


def parse_json_safely(text: str) -> Union[Dict[str, Any], List[Any], None]:
    """Parse JSON from text, handling common LLM formatting issues.
    
    Handles:
    - Markdown code blocks (```json ... ```)
    - Leading/trailing whitespace
    - Common syntax errors (if possible)
    
    Args:
        text: The text containing JSON
        
    Returns:
        Parsed JSON object or None if parsing fails
    """
    if not text:
        return None
        
    # Clean markdown code blocks
    cleaned_text = text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:]
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:]
        
    if cleaned_text.endswith("```"):
        cleaned_text = cleaned_text[:-3]
        
    cleaned_text = cleaned_text.strip()
    
    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        LOGGER.warning(f"Initial JSON parse failed: {e}, attempting repairs...")
        
        # Try to find JSON object boundaries
        try:
            # Look for { ... } or [ ... ]
            json_match = re.search(r'(\{.*\}|\[.*\])', cleaned_text, re.DOTALL)
            if json_match:
                potential_json = json_match.group(1)
                return json.loads(potential_json)
        except Exception:
            pass
            
        LOGGER.error(f"Failed to parse JSON: {e}")
        return None


def extract_field_from_broken_json(text: str, field_name: str) -> Optional[str]:
    """Extract a specific string field from broken JSON using regex.
    
    Useful when JSON structure is invalid but specific fields are needed.
    
    Args:
        text: The text containing broken JSON
        field_name: The key to extract
        
    Returns:
        Extracted value or None
    """
    try:
        # Match "field": "value" pattern
        # Handles escaped quotes within the value
        pattern = f'"{field_name}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"'
        match = re.search(pattern, text, re.DOTALL)
        
        if match:
            value = match.group(1)
            # Unescape common characters
            value = value.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
            return value
            
        return None
    except Exception as e:
        LOGGER.error(f"Regex extraction failed for {field_name}: {e}")
        return None
