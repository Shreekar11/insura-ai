import json
from typing import Optional, Dict, Any

from app.core.base_llm_client import BaseLLMClient
from app.utils.exceptions import APIClientError
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely, extract_field_from_broken_json

LOGGER = get_logger(__name__)


class LLMNormalizer:
    """LLM-based text normalizer for OCR cleanup.
    
    Uses BaseLLMClient for API interactions and centralized JSON parsing.
    """
    
    # System prompt for LLM normalization
    NORMALIZATION_PROMPT = """You are an expert system for Insurance OCR Text Normalization. 
Your role is to convert raw OCR text into clean, structurally correct, 
semantically identical normalized markdown.

STRICT RULES:
- Do NOT change the meaning of the text.
- Do NOT summarize, rewrite, omit, or invent content.
- Do NOT hallucinate missing words or rewrite legal/insurance phrases.
- Output ONLY the cleaned markdown text with no explanations.

---------------------------------------
### NORMALIZATION REQUIREMENTS
---------------------------------------

## 1. Fix OCR text defects (WITHOUT changing meaning)
Correct only structural and formatting issues:
- Fix broken words, merged words, and misplaced hyphens.
  Example: "usefor" → "use for", "purposein" → "purpose in"
- Fix hyphenation errors caused by OCR (e.g., "Suminsured" → "Sum Insured").
- Preserve legitimate hyphenated insurance terms (e.g., “Own-Damage”, “Third-Party”).

## 2. Remove OCR artifacts
Remove:
- Backslashes (`\`, `\\`)
- LaTeX fragments (`$...$`, `\%`, `\\%`)
- Unnecessary parentheses created by OCR (`) .`, `(.`, etc.)
- Duplicate punctuation (`, ,`, `..`, `--`, etc.)
- Page markers like `---`, `===`, page numbers unless part of the text

## 3. Normalize values
- Normalize percentages (“75 \%”, “75 %”, “$75 \%$”) → “75%”
- Normalize bullets/lists:
  - 1., 2., 3.
  - i., ii., iii.
  - Hyphen/asterisk bullets
- Ensure consistent spacing and indentation

## 4. Markdown normalization
- Correct headers (#, ##, ###) and ensure they appear on their own line.
- Add a blank line after every header.
- Convert malformed or partial headers into correct markdown headers.
- Ensure section titles are not merged with following content.

## 5. Paragraph reconstruction
- Insert missing line breaks between paragraphs.
- Join lines that were incorrectly split mid-sentence.
- Do NOT merge paragraphs that should remain separate.

## 6. Table reconstruction (VERY IMPORTANT)
Reconstruct tables into clean markdown table format:

- Detect multi-line headers and merge them into a single row.
- Remove fragment / partial header leftovers.
- Remove blank rows inside tables.
- Ensure consistent pipe `|` formatting:
  
  | Column A | Column B |
  |----------|----------|
  | value    | value    |

- Preserve all table data exactly as written.

## 7. Preserve domain-critical semantics
DO NOT modify:
- Insurance terms
- Legal language
- Policy wordings
- Clause numbers
- Definitions
- Exclusions or inclusions
- Section titles

The text must remain **legally identical** to the source.

## 8. No additions, no exclusions
- Do NOT infer missing content.
- Do NOT rewrite any part of the content.
- Do NOT guess corrected words unless the OCR error is unambiguous (“usefor”, “6months”).
- Do NOT add glossaries, summaries, or commentary.

---------------------------------------
### OUTPUT RULES
---------------------------------------
- Output ONLY the final normalized markdown text.
- Do NOT wrap output in code fences.
- Do NOT include explanations.
- Do NOT include metadata, comments, notes, or system messages.

---------------------------------------
### FINAL GOAL
---------------------------------------
Produce perfectly structured, clean, readable, 
and semantically unchanged insurance markdown text suitable for 
downstream deterministic extraction."""

    # Normalization and signal extraction prompt for classification AND section detection
    NORMALIZATION_AND_SIGNAL_EXTRACTION_PROMPT = """You are an OCR normalizer and metadata extractor specialized in insurance documents.

TASK:
1) Normalize the following OCR chunk according to the STRICT NORMALIZATION REQUIREMENTS below.
2) Detect the section type and subsection type.
3) Extract classification signals for document classes.
4) Return keywords and key entities.

---------------------------------------
### NORMALIZATION REQUIREMENTS
---------------------------------------

## 1. Fix OCR text defects (WITHOUT changing meaning)
Correct only structural and formatting issues:
- Fix broken words, merged words, and misplaced hyphens.
  Example: "usefor" → "use for", "purposein" → "purpose in"
- Fix hyphenation errors caused by OCR (e.g., "Suminsured" → "Sum Insured").
- Preserve legitimate hyphenated insurance terms (e.g., “Own-Damage”, “Third-Party”).

## 2. Remove OCR artifacts
Remove:
- Backslashes (`\`, `\\`)
- LaTeX fragments (`$...$`, `\%`, `\\%`)
- Unnecessary parentheses created by OCR (`) .`, `(.`, etc.)
- Duplicate punctuation (`, ,`, `..`, `--`, etc.)
- Page markers like `---`, `===`, page numbers unless part of the text

## 3. Normalize values
- Normalize percentages (“75 \%”, “75 %”, “$75 \%$”) → “75%”
- Normalize bullets/lists:
  - 1., 2., 3.
  - i., ii., iii.
  - Hyphen/asterisk bullets
- Ensure consistent spacing and indentation

## 4. Markdown normalization
- Correct headers (#, ##, ###) and ensure they appear on their own line.
- Add a blank line after every header.
- Convert malformed or partial headers into correct markdown headers.
- Ensure section titles are not merged with following content.

## 5. Paragraph reconstruction
- Insert missing line breaks between paragraphs.
- Join lines that were incorrectly split mid-sentence.
- Do NOT merge paragraphs that should remain separate.

## 6. Table reconstruction (VERY IMPORTANT)
Reconstruct tables into clean markdown table format:

- Detect multi-line headers and merge them into a single row.
- Remove fragment / partial header leftovers.
- Remove blank rows inside tables.
- Ensure consistent pipe `|` formatting:
  
  | Column A | Column B |
  |----------|----------|
  | value    | value    |

- Preserve all table data exactly as written.

## 7. Preserve domain-critical semantics
DO NOT modify:
- Insurance terms
- Legal language
- Policy wordings
- Clause numbers
- Definitions
- Exclusions or inclusions
- Section titles

The text must remain **legally identical** to the source.

## 8. No additions, no exclusions
- Do NOT infer missing content.
- Do NOT rewrite any part of the content.
- Do NOT guess corrected words unless the OCR error is unambiguous (“usefor”, “6months”).
- Do NOT add glossaries, summaries, or commentary.

---------------------------------------
### EXTRACTION GUIDELINES
---------------------------------------

SECTION DETECTION:
- "Declarations": Policy declarations page, dec page, policy information summary
- "Coverages": Coverage details, limits of insurance, insuring agreements, coverage sections
- "Endorsements": Policy endorsements, attached forms, schedule of forms, modifications
- "SOV": Statement of values, schedule of locations, property schedule, building schedule
- "Loss Run": Loss history, claims history, loss run report, historical claims
- "Schedule": Various schedules (equipment, locations, vehicles)
- "Conditions": Policy conditions, general conditions, terms and conditions
- "Exclusions": Coverage exclusions, what is not covered

CLASSIFICATION SIGNALS (0.0-1.0):
- Classes: [policy, claim, submission, quote, proposal, SOV, financials, loss_run, audit, endorsement, invoice, correspondence]
- "policy": Declarations, coverage details, policy numbers
- "claim": Loss date, claim number, adjuster info
- "submission": Application info, agent details
- "quote": Premium quotes, carrier names
- "SOV": Schedule of Values, property lists
- "loss_run": Historical loss data, claims history

ENTITIES TO EXTRACT:
- policy_number, claim_number, insured_name
- loss_date (YYYY-MM-DD), effective_date (YYYY-MM-DD)
- premium_amount (numeric)

---------------------------------------
### OUTPUT FORMAT
---------------------------------------

CRITICAL JSON FORMATTING RULES:
1. The normalized_text field MUST have all newlines escaped as \\n
2. ALL quotes inside normalized_text MUST be escaped as \\"
3. ALL backslashes inside normalized_text MUST be escaped as \\\\
4. Do NOT include actual newline characters in the JSON
5. Ensure the JSON is on a SINGLE LINE or properly escaped if multiline

RETURN ONLY VALID JSON with exactly these keys:
{"normalized_text": "Text with escaped \\n newlines...", "section_type": "Declarations", "subsection_type": "Named Insured", "section_confidence": 0.92, "signals": {"policy": 0.95, ...}, "keywords": ["Policy Number", ...], "entities": {"policy_number": "12345", ...}, "confidence": 0.92}

EXAMPLE VALID OUTPUT:
{"normalized_text": "Policy Number: 12345\\nInsured: John Doe\\nEffective Date: 2025-01-01", "section_type": "Declarations", "subsection_type": "Named Insured", "section_confidence": 0.95, "signals": {"policy": 0.95, "claim": 0.0, "submission": 0.0, "quote": 0.0, "proposal": 0.0, "SOV": 0.0, "financials": 0.0, "loss_run": 0.0, "audit": 0.0, "endorsement": 0.05, "invoice": 0.0, "correspondence": 0.0}, "keywords": ["Policy Number", "Insured", "Effective Date"], "entities": {"policy_number": "12345", "insured_name": "John Doe", "effective_date": "2025-01-01"}, "confidence": 0.92}

IMPORTANT:
- All 12 document classes MUST be present in signals with scores 0.0-1.0
- Scores should sum to approximately 1.0 but don't need to be exact
- section_type and subsection_type can be null if section is unclear
- section_confidence should reflect your confidence in section detection
- Only include entities that are actually present in the text
- confidence is your overall confidence in the signal extraction (0.0-1.0)
- ENSURE ALL JSON IS PROPERLY ESCAPED AND VALID
"""

    def __init__(
        self,
        openrouter_api_key: str,
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        openrouter_model: str = "google/gemini-2.0-flash-001",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """Initialize LLM text normalizer.
        
        Args:
            openrouter_api_key: OpenRouter API key
            openrouter_api_url: OpenRouter chat completion endpoint
            openrouter_model: Model name to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.openrouter_model = openrouter_model
        
        # Initialize BaseLLMClient
        self.client = BaseLLMClient(
            api_key=openrouter_api_key,
            base_url=openrouter_api_url,
            timeout=timeout,
            max_retries=max_retries
        )
        
        LOGGER.info(
            "Initialized LLM text normalizer",
            extra={
                "model": self.openrouter_model,
                "api_url": openrouter_api_url,
                "timeout": timeout,
            }
        )
    
    async def normalize(self, raw_text: str) -> str:
        """Normalize OCR text using LLM."""
        if not raw_text or not raw_text.strip():
            LOGGER.warning("Empty text provided for LLM normalization")
            return ""
        
        LOGGER.info(
            "Starting LLM text normalization",
            extra={"text_length": len(raw_text)}
        )
        
        try:
            normalized_text = await self._call_llm_api(raw_text)
            
            LOGGER.info(
                "LLM normalization completed successfully",
                extra={
                    "original_length": len(raw_text),
                    "normalized_length": len(normalized_text),
                    "reduction_percent": round(
                        (1 - len(normalized_text) / len(raw_text)) * 100, 2
                    ) if len(raw_text) > 0 else 0.0,
                }
            )
            
            return normalized_text
            
        except Exception as e:
            LOGGER.error(
                "LLM normalization failed, returning original text",
                exc_info=True,
                extra={"error": str(e)}
            )
            # Fallback to original text if LLM fails
            return raw_text
    
    async def normalize_with_signals(self, raw_text: str, page_number: int = 1) -> Dict[str, Any]:
        """Normalize OCR text and extract classification signals."""
        if not raw_text or not raw_text.strip():
            LOGGER.warning("Empty text provided for signal extraction")
            return self._get_empty_result(raw_text)
        
        LOGGER.info(
            "Starting LLM normalization with signal extraction",
            extra={"text_length": len(raw_text), "page_number": page_number}
        )
        
        try:
            result = await self._call_llm_api_with_signals(raw_text, page_number)
            
            LOGGER.info(
                "LLM normalization with signals completed successfully",
                extra={
                    "original_length": len(raw_text),
                    "normalized_length": len(result["normalized_text"]),
                    "section_type": result.get("section_type"),
                    "section_confidence": result.get("section_confidence", 0.0),
                    "top_class": max(result["signals"].items(), key=lambda x: x[1])[0] if result["signals"] else "none",
                }
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(
                "LLM signal extraction failed, returning fallback",
                exc_info=True,
                extra={"error": str(e)}
            )
            return self._get_empty_result(raw_text)
    
    def _get_empty_result(self, text: str) -> Dict[str, Any]:
        """Get empty result structure."""
        return {
            "normalized_text": text,
            "section_type": None,
            "subsection_type": None,
            "section_confidence": 0.0,
            "signals": self._get_default_signals(),
            "keywords": [],
            "entities": {},
            "confidence": 0.0
        }
    
    def _get_default_signals(self) -> Dict[str, float]:
        """Get default signal scores (all zeros)."""
        return {
            "policy": 0.0,
            "claim": 0.0,
            "submission": 0.0,
            "quote": 0.0,
            "proposal": 0.0,
            "SOV": 0.0,
            "financials": 0.0,
            "loss_run": 0.0,
            "audit": 0.0,
            "endorsement": 0.0,
            "invoice": 0.0,
            "correspondence": 0.0,
        }
    
    async def _call_llm_api(self, text: str) -> str:
        """Call LLM API for text normalization."""
        payload = {
            "model": self.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": self.NORMALIZATION_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Normalize this OCR text:\n\n{text}"
                }
            ],
            "temperature": 0.0,
            "max_tokens": len(text) * 2,
        }
        
        # Use BaseLLMClient
        result = await self.client.call_api(
            endpoint="",
            method="POST",
            payload=payload
        )
        
        # Extract normalized text
        try:
            return result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise APIClientError(f"Unexpected API response format: {e}")
    
    async def _call_llm_api_with_signals(self, text: str, page_number: int = 1) -> Dict[str, Any]:
        """Call LLM API for normalization with signal extraction."""
        context_hint = f"This chunk is from page {page_number}." if page_number > 1 else ""
        
        payload = {
            "model": self.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": self.NORMALIZATION_AND_SIGNAL_EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": f"{context_hint}\n\nCHUNK:\n{text}"
                }
            ],
            "temperature": 0.0,
            "max_tokens": len(text) * 3,
        }
        
        # Use BaseLLMClient
        result = await self.client.call_api(
            endpoint="",
            method="POST",
            payload=payload
        )
        
        # Extract content
        try:
            llm_response = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise APIClientError(f"Unexpected API response format: {e}")
            
        # Parse JSON
        return self._parse_signal_response(llm_response)
    
    def _parse_signal_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate LLM response with signal extraction."""
        # Use centralized JSON parser
        parsed = parse_json_safely(response_text)
        
        if not parsed:
            # Try fallback extraction for specific fields if parsing failed
            normalized_text = extract_field_from_broken_json(response_text, "normalized_text")
            if normalized_text:
                parsed = {
                    "normalized_text": normalized_text,
                    "signals": self._get_default_signals(),
                    "keywords": [],
                    "entities": {},
                    "confidence": 0.3
                }
                LOGGER.warning("Extracted only normalized_text from broken JSON")
            else:
                raise APIClientError("Failed to parse LLM response")
        
        # Validate and normalize the parsed response
        if "normalized_text" not in parsed:
            parsed["normalized_text"] = ""
        
        if "signals" not in parsed:
            parsed["signals"] = self._get_default_signals()
        
        # Ensure all document types are present in signals
        default_signals = self._get_default_signals()
        signals = parsed.get("signals", {})
        
        # Fill in missing document types with 0.0
        for doc_type in default_signals.keys():
            if doc_type not in signals:
                signals[doc_type] = 0.0
        
        # Normalize signal values to be within 0.0-1.0
        for doc_type, score in signals.items():
            if not isinstance(score, (int, float)):
                signals[doc_type] = 0.0
            elif score < 0.0:
                signals[doc_type] = 0.0
            elif score > 1.0:
                signals[doc_type] = 1.0
        
        parsed["signals"] = signals
        
        # Set defaults for optional fields
        parsed.setdefault("keywords", [])
        parsed.setdefault("entities", {})
        parsed.setdefault("confidence", 0.5)
        parsed.setdefault("section_type", None)
        parsed.setdefault("subsection_type", None)
        parsed.setdefault("section_confidence", 0.0)
        
        return parsed
