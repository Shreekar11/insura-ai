"""LLM-based text normalizer for OCR output cleanup.

This service uses an LLM (Mistral) to perform structural text normalization,
handling OCR artifacts, hyphenation, table reconstruction, and markdown cleanup.
"""

import httpx
import json
from typing import Optional, Dict, Any

from app.utils.exceptions import APIClientError, OCRTimeoutError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class LLMNormalizer:
    """LLM-based text normalizer for OCR cleanup.
    
    This service uses Mistral's LLM API to perform intelligent text normalization
    that would be difficult or impossible with rule-based approaches:
    - Fix broken words, hyphenation, and merged tokens
    - Remove OCR artifacts (backslashes, LaTeX fragments, escape characters)
    - Normalize tables and reconstruct structure
    - Clean markdown formatting
    - Reconstruct paragraphs and lists
    
    The LLM approach is more robust and maintainable than extensive regex rules.
    
    Attributes:
        api_key: Mistral API key
        api_url: Mistral chat completion endpoint
        model: Model name to use for normalization
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
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

    # Signal extraction prompt for classification
    SIGNAL_EXTRACTION_PROMPT = """You are an OCR normalizer and metadata extractor specialized in insurance documents.

TASK:
1) Normalize the following OCR chunk (fix broken words, hyphenation, remove obvious artifacts, keep tables readable).
2) Extract classification signals for the following document classes:
   [policy, claim, submission, quote, proposal, SOV, financials, loss_run, audit, endorsement, invoice, correspondence]
   
   For each class, provide a numeric score 0.0-1.0 indicating how strongly this chunk suggests that class.
   
3) Return up to 8 short keywords or phrases from the chunk that indicate document type.
   Examples: "Loss Date", "Declarations Page", "Policy Number", "Claim Number", "Premium", "Coverage"
   
4) Extract key entities if present and their normalized forms:
   - policy_number: Policy identification number
   - claim_number: Claim identification number
   - insured_name: Name of the insured party
   - loss_date: Date of loss (YYYY-MM-DD format)
   - effective_date: Policy effective date (YYYY-MM-DD format)
   - premium_amount: Premium amount (numeric)

CLASSIFICATION GUIDELINES:
- "policy": Contains policy declarations, coverage details, policy numbers, insured information
- "claim": Contains loss date, claim number, adjuster info, loss description
- "submission": Contains application info, agent details, quote requests
- "quote": Contains premium quotes, carrier names, coverage options
- "proposal": Contains proposal details, recommendations
- "SOV": Schedule of Values, property lists, TIV (Total Insured Value)
- "financials": Balance sheets, income statements, financial statements
- "loss_run": Historical loss data, claims history
- "audit": Audit reports, compliance documents
- "endorsement": Policy modifications, amendments
- "invoice": Billing statements, payment requests
- "correspondence": Letters, emails, general communication

CRITICAL JSON FORMATTING RULES:
1. The normalized_text field MUST have all newlines escaped as \\n
2. ALL quotes inside normalized_text MUST be escaped as \\"
3. ALL backslashes inside normalized_text MUST be escaped as \\\\
4. Do NOT include actual newline characters in the JSON
5. Ensure the JSON is on a SINGLE LINE or properly escaped if multiline

RETURN ONLY VALID JSON with exactly these keys (no code fences, no explanations, no extra text):
{"normalized_text": "Text with escaped \\n newlines and \\" quotes", "signals": {"policy": 0.12, "claim": 0.78, "submission": 0.05, "quote": 0.02, "proposal": 0.0, "SOV": 0.0, "financials": 0.0, "loss_run": 0.0, "audit": 0.0, "endorsement": 0.0, "invoice": 0.0, "correspondence": 0.03}, "keywords": ["loss date", "insured", "claim number"], "entities": {"claim_number": "CLM-2025-001", "loss_date": "2025-01-10"}, "confidence": 0.87}

EXAMPLE VALID OUTPUT:
{"normalized_text": "Policy Number: 12345\\nInsured: John Doe\\nEffective Date: 2025-01-01", "signals": {"policy": 0.95, "claim": 0.0, "submission": 0.0, "quote": 0.0, "proposal": 0.0, "SOV": 0.0, "financials": 0.0, "loss_run": 0.0, "audit": 0.0, "endorsement": 0.05, "invoice": 0.0, "correspondence": 0.0}, "keywords": ["Policy Number", "Insured", "Effective Date"], "entities": {"policy_number": "12345", "insured_name": "John Doe", "effective_date": "2025-01-01"}, "confidence": 0.92}

IMPORTANT:
- All 12 document classes MUST be present in signals with scores 0.0-1.0
- Scores should sum to approximately 1.0 but don't need to be exact
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
            openrouter_model: Model name to use (default: google/gemini-2.0-flash-001)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_api_url = openrouter_api_url
        self.openrouter_model = openrouter_model
        self.timeout = timeout
        self.max_retries = max_retries
        
        LOGGER.info(
            "Initialized LLM text normalizer",
            extra={
                "model": self.openrouter_model,
                "api_url": self.openrouter_api_url,
                "timeout": self.timeout,
            }
        )
    
    async def normalize(self, raw_text: str) -> str:
        """Normalize OCR text using LLM.
        
        This method sends the raw OCR text to the LLM with instructions
        to clean and normalize it. If the LLM call fails, it returns the
        original text as a fallback.
        
        Args:
            raw_text: Raw OCR-extracted text to normalize
            
        Returns:
            str: Normalized text (or original text if LLM call fails)
            
        Example:
            >>> normalizer = LLMNormalizer(api_key="...")
            >>> raw = "PoIicy Num- ber: 12345\\n\\nPage 1 of 5"
            >>> clean = await normalizer.normalize(raw)
            >>> print(clean)
            Policy Number: 12345
        """
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
        """Normalize OCR text and extract classification signals.
        
        This method performs both normalization and classification signal extraction
        in a single LLM call, making it cost-efficient for classification pipelines.
        
        Args:
            raw_text: Raw OCR-extracted text to normalize
            page_number: Page number for context (optional)
            
        Returns:
            dict: Dictionary containing:
                - normalized_text: Cleaned text
                - signals: Per-class confidence scores
                - keywords: Extracted keywords
                - entities: Extracted entities
                - confidence: Overall extraction confidence
                
        Example:
            >>> normalizer = LLMNormalizer(api_key="...")
            >>> result = await normalizer.normalize_with_signals(chunk_text)
            >>> print(result["signals"]["claim"])  # 0.78
            >>> print(result["entities"]["claim_number"])  # "CLM-2025-001"
        """
        if not raw_text or not raw_text.strip():
            LOGGER.warning("Empty text provided for signal extraction")
            return {
                "normalized_text": "",
                "signals": self._get_default_signals(),
                "keywords": [],
                "entities": {},
                "confidence": 0.0
            }
        
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
                    "top_class": max(result["signals"].items(), key=lambda x: x[1])[0],
                    "top_score": max(result["signals"].values()),
                    "keywords_count": len(result.get("keywords", [])),
                    "entities_count": len(result.get("entities", {})),
                }
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(
                "LLM signal extraction failed, returning fallback",
                exc_info=True,
                extra={"error": str(e)}
            )
            # Fallback: return normalized text without signals
            return {
                "normalized_text": raw_text,
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
        """Call LLM API for text normalization.
        
        Args:
            text: Text to normalize
            
        Returns:
            str: Normalized text from LLM
            
        Raises:
            APIClientError: If API call fails after retries
            OCRTimeoutError: If API call times out
        """
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        
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
            "temperature": 0.0,  # Deterministic output
            "max_tokens": len(text) * 2,  # Allow for some expansion
        }
        
        LOGGER.debug(
            "Calling OpenRouter LLM API for normalization",
            extra={"model": self.openrouter_model, "text_length": len(text)}
        )
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        self.openrouter_api_url,
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # Extract normalized text from response
                    normalized_text = result["choices"][0]["message"]["content"].strip()
                    
                    LOGGER.debug(
                        "LLM API call successful",
                        extra={
                            "attempt": attempt + 1,
                            "input_length": len(text),
                            "output_length": len(normalized_text),
                        }
                    )
                    
                    return normalized_text
                    
                except httpx.HTTPStatusError as e:
                    await self._handle_http_error(e, attempt)
                    
                except httpx.TimeoutException as e:
                    await self._handle_timeout_error(e, attempt)
                    
                except Exception as e:
                    await self._handle_generic_error(e, attempt)
        
        raise APIClientError("Failed to normalize text after all retry attempts")
    
    async def _call_llm_api_with_signals(self, text: str, page_number: int = 1) -> Dict[str, Any]:
        """Call LLM API for normalization with signal extraction.
        
        Args:
            text: Text to normalize
            page_number: Page number for context
            
        Returns:
            dict: Parsed JSON response with normalized_text, signals, keywords, entities
            
        Raises:
            APIClientError: If API call fails after retries
            OCRTimeoutError: If API call times out
        """
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        
        # Add page context to the prompt
        context_hint = f"This chunk is from page {page_number}." if page_number > 1 else ""
        
        payload = {
            "model": self.openrouter_model,
            "messages": [
                {
                    "role": "system",
                    "content": self.SIGNAL_EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": f"{context_hint}\n\nCHUNK:\n{text}"
                }
            ],
            "temperature": 0.0,  # Deterministic output
            "max_tokens": len(text) * 3,  # Allow for expansion + JSON structure
        }
        
        LOGGER.debug(
            "Calling OpenRouter LLM API for signal extraction",
            extra={"model": self.openrouter_model, "text_length": len(text), "page": page_number}
        )
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries):
                try:
                    response = await client.post(
                        self.openrouter_api_url,
                        json=payload,
                        headers=headers
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # Extract LLM response
                    llm_response = result["choices"][0]["message"]["content"].strip()
                    
                    # Parse JSON response
                    parsed_result = self._parse_signal_response(llm_response)
                    
                    LOGGER.debug(
                        "LLM API call with signals successful",
                        extra={
                            "attempt": attempt + 1,
                            "input_length": len(text),
                            "output_length": len(parsed_result["normalized_text"]),
                            "top_signal": max(parsed_result["signals"].items(), key=lambda x: x[1])[0],
                        }
                    )
                    
                    return parsed_result
                    
                except httpx.HTTPStatusError as e:
                    await self._handle_http_error(e, attempt)
                    
                except httpx.TimeoutException as e:
                    await self._handle_timeout_error(e, attempt)
                    
                except json.JSONDecodeError as e:
                    LOGGER.error(
                        f"Failed to parse JSON response from LLM: {str(e)}",
                        extra={"response": llm_response if 'llm_response' in locals() else "N/A"}
                    )
                    if attempt < self.max_retries - 1:
                        await self._wait_before_retry(attempt)
                    else:
                        raise APIClientError(f"Failed to parse LLM JSON response: {str(e)}") from e
                    
                except Exception as e:
                    await self._handle_generic_error(e, attempt)
        
        raise APIClientError("Failed to extract signals after all retry attempts")
    
    def _parse_signal_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate LLM response with signal extraction.
        
        Args:
            response_text: Raw LLM response text
            
        Returns:
            Dict with normalized_text, signals, keywords, entities
            
        Raises:
            ValueError: If response cannot be parsed
        """
        import re
        
        try:
            # Clean response - remove markdown code fences
            cleaned_response = response_text.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            # Try to parse JSON
            try:
                parsed = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                LOGGER.warning(f"Initial JSON parse failed: {e}, attempting repairs...")
                
                # Strategy 1: Manual field extraction using regex (most reliable for broken JSON)
                try:
                    # Extract normalized_text - handle multiline content
                    # Match everything between "normalized_text": " and the next ", accounting for escaped quotes
                    norm_match = re.search(
                        r'"normalized_text"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,',
                        cleaned_response,
                        re.DOTALL
                    )
                    if not norm_match:
                        # Try alternate pattern - the field might be at the end or have different spacing
                        norm_match = re.search(
                            r'"normalized_text"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
                            cleaned_response,
                            re.DOTALL
                        )
                    
                    normalized_text = ""
                    if norm_match:
                        # Unescape the content
                        normalized_text = norm_match.group(1)
                        normalized_text = normalized_text.replace('\\n', '\n')
                        normalized_text = normalized_text.replace('\\t', '\t')
                        normalized_text = normalized_text.replace('\\"', '"')
                        normalized_text = normalized_text.replace('\\\\', '\\')
                    else:
                        LOGGER.warning("Could not extract normalized_text field")
                    
                    # Extract signals object
                    signals_match = re.search(r'"signals"\s*:\s*\{([^}]+)\}', cleaned_response)
                    signals = {}
                    if signals_match:
                        signals_str = signals_match.group(1)
                        # Parse each signal
                        for signal_match in re.finditer(r'"(\w+)"\s*:\s*([\d.]+)', signals_str):
                            try:
                                signals[signal_match.group(1)] = float(signal_match.group(2))
                            except ValueError:
                                LOGGER.warning(f"Invalid signal value for {signal_match.group(1)}")
                                signals[signal_match.group(1)] = 0.0
                    
                    # Extract keywords array
                    keywords_match = re.search(r'"keywords"\s*:\s*\[([^\]]*)\]', cleaned_response)
                    keywords = []
                    if keywords_match:
                        keywords_str = keywords_match.group(1)
                        # Extract quoted strings
                        keywords = re.findall(r'"([^"]*)"', keywords_str)
                    
                    # Extract entities object
                    entities_match = re.search(r'"entities"\s*:\s*\{([^}]*)\}', cleaned_response)
                    entities = {}
                    if entities_match:
                        entities_str = entities_match.group(1)
                        # Extract key-value pairs
                        for entity_match in re.finditer(r'"(\w+)"\s*:\s*"([^"]*)"', entities_str):
                            entities[entity_match.group(1)] = entity_match.group(2)
                        # Also handle numeric values
                        for entity_match in re.finditer(r'"(\w+)"\s*:\s*([\d.]+)', entities_str):
                            if entity_match.group(1) not in entities:  # Don't override string values
                                try:
                                    entities[entity_match.group(1)] = float(entity_match.group(2))
                                except ValueError:
                                    pass
                    
                    # Extract confidence
                    confidence_match = re.search(r'"confidence"\s*:\s*([\d.]+)', cleaned_response)
                    confidence = float(confidence_match.group(1)) if confidence_match else 0.5
                    
                    # Build response
                    parsed = {
                        "normalized_text": normalized_text,
                        "signals": signals if signals else self._get_default_signals(),
                        "keywords": keywords,
                        "entities": entities,
                        "confidence": confidence
                    }
                    
                    LOGGER.info("Successfully extracted data using manual field parsing")
                    
                except Exception as e3:
                    LOGGER.error(f"Manual field extraction failed: {e3}")
                    
                    # Last resort: Try to at least get normalized_text by looking for the pattern
                    # even if it spans multiple lines and has unescaped content
                    try:
                        # Find the start of normalized_text
                        start_match = re.search(r'"normalized_text"\s*:\s*"', cleaned_response)
                        if start_match:
                            start_pos = start_match.end()
                            # Find the end by looking for ",\s*"signals"
                            end_match = re.search(r'",\s*"signals"', cleaned_response[start_pos:])
                            if end_match:
                                # Extract the text between
                                normalized_text = cleaned_response[start_pos:start_pos + end_match.start()]
                                # Basic cleanup
                                normalized_text = normalized_text.replace('\\n', '\n').replace('\\"', '"')
                                
                                parsed = {
                                    "normalized_text": normalized_text,
                                    "signals": self._get_default_signals(),
                                    "keywords": [],
                                    "entities": {},
                                    "confidence": 0.3
                                }
                                LOGGER.warning("Extracted only normalized_text, using defaults for other fields")
                            else:
                                raise ValueError("Could not find normalized_text boundaries")
                        else:
                            raise ValueError("Could not find normalized_text field")
                    except Exception as e4:
                        LOGGER.error(f"All parsing strategies failed: {e4}")
                        raise ValueError(f"Could not parse LLM response after all repair attempts: {str(e4)}")
            
            # Validate and normalize the parsed response
            if "normalized_text" not in parsed:
                LOGGER.warning("Response missing 'normalized_text' field, using empty string")
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
            if "keywords" not in parsed:
                parsed["keywords"] = []
            if "entities" not in parsed:
                parsed["entities"] = {}
            if "confidence" not in parsed:
                parsed["confidence"] = 0.5
            
            # Ensure confidence is valid
            confidence = parsed.get("confidence", 0.5)
            if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
                parsed["confidence"] = 0.5
            
            return parsed
            
        except Exception as e:
            LOGGER.error(f"Failed to parse signal response: {e}")
            LOGGER.debug(f"Raw response (first 1000 chars): {response_text[:1000]}...")
            # Return a safe fallback instead of raising
            return {
                "normalized_text": "",
                "signals": self._get_default_signals(),
                "keywords": [],
                "entities": {},
                "confidence": 0.0
            }
    
    async def _handle_http_error(
        self,
        error: httpx.HTTPStatusError,
        attempt: int,
    ) -> None:
        """Handle HTTP status errors with retry logic.
        
        Args:
            error: The HTTP status error
            attempt: Current attempt number
            
        Raises:
            APIClientError: If all retries exhausted
        """
        # Log the actual API response for debugging
        try:
            error_detail = error.response.json()
            LOGGER.error(
                f"LLM API error response: {error_detail}",
                extra={"status_code": error.response.status_code}
            )
        except Exception:
            LOGGER.error(
                f"LLM API error response (text): {error.response.text}",
                extra={"status_code": error.response.status_code}
            )
        
        if attempt < self.max_retries - 1:
            LOGGER.warning(
                f"LLM API call failed, retrying (attempt {attempt + 1}/{self.max_retries})",
                extra={
                    "status_code": error.response.status_code,
                    "error": str(error),
                }
            )
            await self._wait_before_retry(attempt)
        else:
            LOGGER.error(
                "LLM API call failed after all retries",
                exc_info=True,
                extra={"status_code": error.response.status_code}
            )
            raise APIClientError(
                f"LLM API returned error: {error.response.status_code}"
            ) from error
    
    async def _handle_timeout_error(
        self,
        error: httpx.TimeoutException,
        attempt: int,
    ) -> None:
        """Handle timeout errors with retry logic.
        
        Args:
            error: The timeout error
            attempt: Current attempt number
            
        Raises:
            OCRTimeoutError: If all retries exhausted
        """
        if attempt < self.max_retries - 1:
            LOGGER.warning(
                f"LLM API call timed out, retrying (attempt {attempt + 1}/{self.max_retries})",
                extra={"error": str(error)}
            )
            await self._wait_before_retry(attempt)
        else:
            LOGGER.error(
                "LLM API call timed out after all retries",
                exc_info=True
            )
            raise OCRTimeoutError(
                f"LLM normalization timed out after {self.timeout}s"
            ) from error
    
    async def _handle_generic_error(
        self,
        error: Exception,
        attempt: int,
    ) -> None:
        """Handle generic errors with retry logic.
        
        Args:
            error: The generic error
            attempt: Current attempt number
            
        Raises:
            APIClientError: If all retries exhausted
        """
        if attempt < self.max_retries - 1:
            LOGGER.warning(
                f"LLM API call failed, retrying (attempt {attempt + 1}/{self.max_retries})",
                extra={"error": str(error)}
            )
            await self._wait_before_retry(attempt)
        else:
            LOGGER.error(
                "LLM API call failed after all retries",
                exc_info=True
            )
            raise APIClientError(
                f"Failed to call LLM API: {str(error)}"
            ) from error
    
    async def _wait_before_retry(self, attempt: int) -> None:
        """Wait before retrying with exponential backoff.
        
        Args:
            attempt: Current attempt number (0-indexed)
        """
        import asyncio
        
        # Exponential backoff: 2, 4, 8 seconds
        wait_time = 2 * (2 ** attempt)
        LOGGER.debug("Waiting before retry", extra={"wait_seconds": wait_time})
        await asyncio.sleep(wait_time)
