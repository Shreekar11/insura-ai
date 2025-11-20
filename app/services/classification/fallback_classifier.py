"""Fallback classifier for low-confidence documents.

This service performs a final LLM-based classification when signal aggregation
fails to reach the acceptance threshold. It uses a summary of the document
(keywords + top chunks) to make a decision.
"""

import json
import httpx
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
        openrouter_api_key: str,
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        openrouter_model: str = "google/gemini-2.0-flash-001",
        timeout: int = 30,
    ):
        self.api_key = openrouter_api_key
        self.api_url = openrouter_api_url
        self.model = openrouter_model
        self.timeout = timeout

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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.api_url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

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
