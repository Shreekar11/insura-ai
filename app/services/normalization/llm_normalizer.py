"""LLM-based text normalizer for OCR output cleanup.

This service uses an LLM (Mistral) to perform structural text normalization,
handling OCR artifacts, hyphenation, table reconstruction, and markdown cleanup.
"""

import httpx
from typing import Optional

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
