import json
from typing import Optional, Dict, Any

from app.core.unified_llm import UnifiedLLMClient, LLMProvider
from app.prompts import SINGLE_CHUNK_NORMALIZATION_PROMPT, SIMPLE_NORMALIZATION_PROMPT
from app.utils.exceptions import APIClientError
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely, extract_field_from_broken_json

LOGGER = get_logger(__name__)


class LLMNormalizer:
    """LLM-based text normalizer for OCR cleanup.
    
    Uses UnifiedLLMClient for provider-agnostic LLM interactions.
    """
    
    def __init__(
        self,
        provider: str = "openrouter",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "google/gemini-2.0-flash-001",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        enable_fallback: bool = False,
    ):
        """Initialize LLM normalizer.
        
        Args:
            provider: LLM provider to use ("gemini" or "openrouter")
            gemini_api_key: Gemini API key
            gemini_model: Gemini model name
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model name
            openrouter_api_url: OpenRouter API URL
            enable_fallback: Whether to enable fallback to Gemini if OpenRouter fails
        """
        self.provider = provider
        
        # Initialize UnifiedLLMClient
        self.client = UnifiedLLMClient(
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=openrouter_model,
            openrouter_api_url=openrouter_api_url,
            enable_fallback=enable_fallback
        )
        
        LOGGER.info(
            "Initialized LLM text normalizer",
            extra={
                "provider": provider,
                "model": openrouter_model if provider == "openrouter" else gemini_model,
                "fallback_enabled": enable_fallback and provider == "openrouter",
            }
        )
    
    async def normalize_text(self, text: str) -> str:
        """Normalize text using LLM.
        
        Args:
            text: Raw OCR text
            
        Returns:
            Normalized text
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for LLM normalization")
            return ""
            
        LOGGER.info(
            "Starting LLM text normalization",
            extra={"text_length": len(text)}
        )
        
        try:
            normalized_text = await self._call_llm_api(text)
            
            LOGGER.info(
                "LLM normalization completed successfully",
                extra={
                    "original_length": len(text),
                    "normalized_length": len(normalized_text),
                    "reduction_percent": round(
                        (1 - len(normalized_text) / len(text)) * 100, 2
                    ) if len(text) > 0 else 0.0,
                }
            )
            return normalized_text
        except Exception as e:
            LOGGER.error(
                "LLM normalization failed, returning original text",
                exc_info=True,
                extra={"error": str(e)}
            )
            # Return original text on failure
            return text
    
    async def normalize_with_signals(self, text: str, page_number: int = 1) -> Dict[str, Any]:
        """Normalize text and extract classification signals.
        
        Args:
            text: Raw OCR text
            page_number: Page number for context
            
        Returns:
            Dictionary with normalized_text, section_type, signals, entities
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for signal extraction")
            return self._get_empty_result(text)
            
        LOGGER.info(
            "Starting LLM normalization with signal extraction",
            extra={"text_length": len(text), "page_number": page_number}
        )
        
        try:
            llm_response = await self._call_llm_api_with_signals(text, page_number)
            
            LOGGER.info(
                "LLM normalization with signals completed successfully",
                extra={
                    "original_length": len(text),
                    "normalized_length": len(llm_response["normalized_text"]),
                    "section_type": llm_response.get("section_type"),
                    "section_confidence": llm_response.get("section_confidence", 0.0),
                    "top_class": max(llm_response["signals"].items(), key=lambda x: x[1])[0] if llm_response["signals"] else "none",
                }
            )
            return llm_response
        except Exception as e:
            LOGGER.error(
                "LLM signal extraction failed, returning fallback",
                exc_info=True,
                extra={"error": str(e)}
            )
            return self._get_empty_result(text)
    
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
        # Use GeminiClient
        return await self.client.generate_content(
            contents=f"Normalize this OCR text:\n\n{text}",
            system_instruction=SIMPLE_NORMALIZATION_PROMPT
        )
    
    async def _call_llm_api_with_signals(self, text: str, page_number: int = 1) -> Dict[str, Any]:
        """Call LLM API for normalization with signal extraction."""
        context_hint = f"This chunk is from page {page_number}." if page_number > 1 else ""
        
        # Use GeminiClient
        llm_response = await self.client.generate_content(
            contents=f"{context_hint}\n\nCHUNK:\n{text}",
            system_instruction=SINGLE_CHUNK_NORMALIZATION_PROMPT,
            generation_config={"response_mime_type": "application/json"}
        )
            
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
