"""Base extractor interface for structured data extraction.

This module defines the abstract base class that all extractors must implement,
providing a consistent interface and shared utilities for LLM-based extraction.
"""

import httpx
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.exceptions import APIClientError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class BaseExtractor(ABC):
    """Abstract base class for all extractors.
    
    This class provides:
    - Common interface via abstract extract() method
    - Shared LLM API calling logic
    - Common JSON parsing and validation
    - Utility methods for data type conversion
    
    Attributes:
        session: SQLAlchemy async session
        openrouter_api_key: OpenRouter API key
        openrouter_api_url: OpenRouter API URL
        openrouter_model: Model to use for extraction
    """
    
    def __init__(
        self,
        session: AsyncSession,
        openrouter_api_key: str,
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        openrouter_model: str = "google/gemini-2.0-flash-001",
    ):
        """Initialize base extractor.
        
        Args:
            session: SQLAlchemy async session
            openrouter_api_key: OpenRouter API key
            openrouter_api_url: OpenRouter API URL
            openrouter_model: Model to use
        """
        self.session = session
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_api_url = openrouter_api_url
        self.openrouter_model = openrouter_model
        
        LOGGER.info(f"Initialized {self.__class__.__name__}")
    
    @abstractmethod
    async def extract(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract structured data from text.
        
        This method must be implemented by all subclasses.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List of extracted database model instances
        """
        pass
    
    @abstractmethod
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for this extractor.
        
        This method must be implemented by all subclasses.
        
        Returns:
            str: System prompt for LLM extraction
        """
        pass
    
    async def _call_llm_api(self, text: str) -> List[Dict[str, Any]]:
        """Call LLM API for extraction.
        
        This is a shared method that all extractors can use.
        
        Args:
            text: Text to extract from
            
        Returns:
            List[Dict[str, Any]]: Parsed extraction results
            
        Raises:
            APIClientError: If API call fails
        """
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.openrouter_model,
            "messages": [
                {"role": "system", "content": self.get_extraction_prompt()},
                {"role": "user", "content": f"Text:\n{text}"}
            ],
            "temperature": 0.0,
            "max_tokens": 4000,
        }
        
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.openrouter_api_url,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                
                result = response.json()
                llm_response = result["choices"][0]["message"]["content"].strip()
                
                # Parse JSON
                return self._parse_json_response(llm_response)
                
        except httpx.HTTPError as e:
            LOGGER.error(f"LLM API call failed: {e}", exc_info=True)
            raise APIClientError(f"LLM API call failed: {e}") from e
        except Exception as e:
            LOGGER.error(f"Unexpected error during LLM call: {e}", exc_info=True)
            raise
    
    def _parse_json_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse JSON response from LLM.
        
        Handles common formatting issues like code fences.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            List[Dict[str, Any]]: Parsed JSON data
        """
        try:
            # Clean response
            cleaned = response_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # Parse JSON
            parsed = json.loads(cleaned)
            
            if not isinstance(parsed, list):
                LOGGER.warning(
                    f"{self.__class__.__name__}: Response is not a list, wrapping in list"
                )
                return [parsed] if isinstance(parsed, dict) else []
            
            return parsed
            
        except json.JSONDecodeError as e:
            LOGGER.error(
                f"{self.__class__.__name__}: Failed to parse JSON: {e}",
                extra={"response": response_text[:500]}
            )
            return []
    
    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """Parse date string to datetime.
        
        Args:
            date_str: Date string in YYYY-MM-DD format
            
        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None
        try:
            if isinstance(date_str, str):
                return datetime.strptime(date_str, "%Y-%m-%d")
            return None
        except Exception as e:
            LOGGER.warning(f"Failed to parse date '{date_str}': {e}")
            return None
    
    def _to_decimal(self, value: Any) -> Optional[Decimal]:
        """Convert value to Decimal.
        
        Args:
            value: Numeric value (int, float, str, or Decimal)
            
        Returns:
            Decimal object or None if conversion fails
        """
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except Exception as e:
            LOGGER.warning(f"Failed to convert '{value}' to Decimal: {e}")
            return None
    
    def _to_int(self, value: Any) -> Optional[int]:
        """Convert value to int.
        
        Args:
            value: Numeric value
            
        Returns:
            int or None if conversion fails
        """
        if value is None:
            return None
        try:
            return int(value)
        except Exception as e:
            LOGGER.warning(f"Failed to convert '{value}' to int: {e}")
            return None
