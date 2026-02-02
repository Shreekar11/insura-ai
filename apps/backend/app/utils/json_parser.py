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
    - Concatenated JSON objects (e.g., {...}\n{...})
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

        # Check for "Extra data" error - indicates concatenated JSON
        if "Extra data" in str(e):
            merged = _parse_concatenated_json(cleaned_text)
            if merged is not None:
                LOGGER.info(f"Successfully parsed concatenated JSON, merged into single result")
                return merged

        # Try to find JSON object boundaries (non-greedy for first complete object)
        try:
            # First, try to parse just until the error position
            if hasattr(e, 'pos') and e.pos > 0:
                first_part = cleaned_text[:e.pos].strip()
                if first_part:
                    result = json.loads(first_part)
                    LOGGER.info(f"Parsed first JSON object (truncated at position {e.pos})")
                    return result
        except Exception:
            pass

        # Fallback: Look for { ... } or [ ... ] with non-greedy match
        try:
            # Try non-greedy match first for the first complete object
            json_match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', cleaned_text, re.DOTALL)
            if json_match:
                potential_json = json_match.group(1)
                return json.loads(potential_json)

            # Try array match
            json_match = re.search(r'(\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])', cleaned_text, re.DOTALL)
            if json_match:
                potential_json = json_match.group(1)
                return json.loads(potential_json)
        except Exception:
            pass

        LOGGER.error(f"Failed to parse JSON: {e}")
        return None


def _parse_concatenated_json(text: str) -> Union[Dict[str, Any], List[Any], None]:
    """Parse concatenated JSON objects and merge them.

    Handles cases where LLMs return multiple JSON objects like:
    - {...}\n{...} -> merged dict or list of dicts
    - [...]\n[...] -> merged/flattened list

    Args:
        text: Text containing potentially concatenated JSON

    Returns:
        Merged result or None if parsing fails
    """
    # Strategy 1: Split on }\n{ pattern (objects separated by newline)
    # Also handle }\r\n{ and }  { (multiple spaces)
    split_pattern = r'\}\s*\n\s*\{'

    if re.search(split_pattern, text):
        parts = re.split(split_pattern, text)
        # Restore the braces that were consumed by split
        parts = [parts[0] + '}'] + ['{' + p + '}' for p in parts[1:-1]] + ['{' + parts[-1]]

        parsed_objects = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            try:
                parsed = json.loads(part)
                parsed_objects.append(parsed)
            except json.JSONDecodeError as e:
                LOGGER.debug(f"Failed to parse fragment {i}: {e}")
                continue

        if parsed_objects:
            return _merge_json_objects(parsed_objects)

    # Strategy 2: Split on ]\n[ pattern (arrays separated by newline)
    array_split_pattern = r'\]\s*\n\s*\['

    if re.search(array_split_pattern, text):
        parts = re.split(array_split_pattern, text)
        parts = [parts[0] + ']'] + ['[' + p + ']' for p in parts[1:-1]] + ['[' + parts[-1]]

        all_items = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            try:
                parsed = json.loads(part)
                if isinstance(parsed, list):
                    all_items.extend(parsed)
                else:
                    all_items.append(parsed)
            except json.JSONDecodeError as e:
                LOGGER.debug(f"Failed to parse array fragment {i}: {e}")
                continue

        if all_items:
            return all_items

    # Strategy 3: Use json.JSONDecoder to parse multiple objects
    decoder = json.JSONDecoder()
    results = []
    idx = 0
    text = text.strip()

    while idx < len(text):
        # Skip whitespace
        while idx < len(text) and text[idx] in ' \t\n\r':
            idx += 1
        if idx >= len(text):
            break

        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            results.append(obj)
            idx += end_idx
        except json.JSONDecodeError:
            # Try to find next { or [
            next_brace = text.find('{', idx + 1)
            next_bracket = text.find('[', idx + 1)

            if next_brace == -1 and next_bracket == -1:
                break
            elif next_brace == -1:
                idx = next_bracket
            elif next_bracket == -1:
                idx = next_brace
            else:
                idx = min(next_brace, next_bracket)

    if results:
        return _merge_json_objects(results)

    return None


def _merge_json_objects(objects: List[Any]) -> Union[Dict[str, Any], List[Any]]:
    """Merge a list of parsed JSON objects into a single result.

    Args:
        objects: List of parsed JSON objects/arrays

    Returns:
        Merged result
    """
    if not objects:
        return None

    if len(objects) == 1:
        return objects[0]

    # If all objects are dicts, merge them
    if all(isinstance(obj, dict) for obj in objects):
        merged = {}
        for obj in objects:
            for key, value in obj.items():
                if key in merged:
                    # If key exists, try to merge intelligently
                    existing = merged[key]
                    if isinstance(existing, list) and isinstance(value, list):
                        merged[key] = existing + value
                    elif isinstance(existing, dict) and isinstance(value, dict):
                        merged[key] = {**existing, **value}
                    else:
                        # For conflicts, prefer later value but log
                        LOGGER.debug(f"Key conflict during merge: {key}, using later value")
                        merged[key] = value
                else:
                    merged[key] = value
        return merged

    # If all objects are lists, flatten them
    if all(isinstance(obj, list) for obj in objects):
        flattened = []
        for obj in objects:
            flattened.extend(obj)
        return flattened

    # Mixed types - return as list
    return objects


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
