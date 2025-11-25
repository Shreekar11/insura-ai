"""Fallback classifier for low-confidence documents.

This service performs a final LLM-based classification when signal aggregation
fails to reach the acceptance threshold. It uses a summary of the document
(keywords + top chunks) to make a decision.
"""

import json
from app.core.gemini_client import GeminiClient
from typing import Dict, Any, List, Optional

from app.utils.exceptions import APIClientError
from app.utils.logging import get_logger
from app.services.classification.constants import DOCUMENT_TYPES

LOGGER = get_logger(__name__)


class FallbackClassifier:
    """LLM-based fallback classifier."""
    
    FALLBACK_PROMPT = """You are an expert insurance document classifier.
    
TASK: Classify the following document based on the provided summary and keywords.
Choose EXACTLY ONE type from this list:
{doc_types}

INPUT SUMMARY:
{summary}

RETURN JSON ONLY:
{{
  "classified_type": "...",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}
"""

    def __init__(
        self,
        gemini_api_key: str,
        gemini_model: str = "gemini-2.0-flash",
        timeout: int = 30,
        openrouter_api_url: str = None, # Deprecated
    ):
        self.gemini_model = gemini_model
        # Initialize GeminiClient
        self.client = GeminiClient(
            api_key=gemini_api_key,
            model=gemini_model,
            timeout=timeout,
            max_retries=3
        )

    async def classify(
        self,
        keywords: List[str],
        top_chunks_text: List[str],
        aggregated_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """Perform fallback classification using LLM.
        
        Args:
            keywords: List of extracted keywords
            top_chunks_text: Text from most relevant chunks
            aggregated_scores: Scores from signal aggregation
            
        Returns:
            Dict with classified_type, confidence, reasoning
        """
        # Prepare summary
        summary = f"KEYWORDS: {', '.join(keywords[:20])}\n\n"
        summary += "TOP CHUNKS:\n" + "\n---\n".join(top_chunks_text[:3])
        summary += "\n\nPRELIMINARY SCORES:\n" + str(aggregated_scores)
        
        prompt = self.FALLBACK_PROMPT.format(
            doc_types=DOCUMENT_TYPES,
            summary=summary
        )
        
        try:
            response = await self._call_llm(prompt)
            return self._parse_response(response)
        except Exception as e:
            LOGGER.error(f"Fallback classification failed: {e}")
            return {
                "classified_type": "correspondence",  # Safe default
                "confidence": 0.0,
                "reasoning": f"Fallback failed: {str(e)}"
            }

    async def _call_llm(self, prompt: str) -> str:
        # Use GeminiClient
        return await self.client.generate_content(
            contents=prompt,
            generation_config={"response_mime_type": "application/json"}
        )

    def _parse_response(self, text: str) -> Dict[str, Any]:
        try:
            # Clean code fences
            text = text.strip()
            if text.startswith("```json"): text = text[7:]
            if text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]
            
            data = json.loads(text.strip())
            
            # Validate
            if data.get("classified_type") not in DOCUMENT_TYPES:
                data["classified_type"] = "correspondence"
                data["confidence"] = 0.1
                
            return data
        except Exception as e:
            LOGGER.error(f"Failed to parse fallback response: {e}")
            return {
                "classified_type": "correspondence",
                "confidence": 0.0,
                "reasoning": "Parse error"
            }
