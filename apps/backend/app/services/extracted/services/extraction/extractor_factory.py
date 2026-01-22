"""Extractor factory for dynamic extractor selection and instantiation.

This module implements the Factory Pattern for scalable extraction routing.
It maintains a registry of extractors and dispatches to the appropriate
extractor based on section type.
"""

from typing import Dict, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extracted.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ExtractorFactory:
    """Factory for creating and managing extractors.
    
    This factory:
    - Maintains a registry mapping section types to extractor classes
    - Supports multiple aliases for the same extractor (e.g., "SOV", "Schedule of Values")
    - Dynamically instantiates extractors with dependency injection
    - Provides fallback to DefaultExtractor for unknown types
    
    Attributes:
        session: SQLAlchemy async session
        openrouter_api_key: OpenRouter API key
        openrouter_api_url: OpenRouter API URL
        openrouter_model: Model to use for extraction
        _registry: Mapping of normalized section types to extractor classes
        _instances: Cache of instantiated extractors
    """
    
    def __init__(
        self,
        session: AsyncSession,
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
    ):
        """Initialize extractor factory.
        
        Args:
            session: SQLAlchemy async session
            provider: LLM provider to use ("gemini" or "openrouter")
            gemini_api_key: Gemini API key
            gemini_model: Gemini model to use
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model to use
            openrouter_api_url: OpenRouter API URL
        """
        self.session = session
        self.provider = provider
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_model = openrouter_model
        self.openrouter_api_url = openrouter_api_url
        
        # Registry mapping section types to extractor classes
        self._registry: Dict[str, Type[BaseExtractor]] = {}
        
        # Cache of instantiated extractors
        self._instances: Dict[str, BaseExtractor] = {}
        
        LOGGER.info(
            "Initialized ExtractorFactory",
            extra={
                "registered_types": len(self._registry),
                "provider": provider,
                "model": gemini_model if provider == "gemini" else openrouter_model
            }
        )
    
    def register_extractor(
        self,
        section_types: List[str],
        extractor_class: Type[BaseExtractor]
    ):
        """Register an extractor for multiple section types.
        
        Args:
            section_types: List of section type strings (will be normalized)
            extractor_class: Extractor class to instantiate
        """
        for section_type in section_types:
            normalized = self._normalize_section_type(section_type)
            self._registry[normalized] = extractor_class
            
        LOGGER.debug(
            f"Registered {extractor_class.__name__} for {len(section_types)} section types"
        )
    
    def get_extractor(self, section_type: str) -> Optional[BaseExtractor]:
        """Get the appropriate extractor for a section type.
        
        Args:
            section_type: Section type string from chunk metadata
            
        Returns:
            BaseExtractor: Instantiated extractor or None
        """
        if not section_type:
            return None
        
        normalized = self._normalize_section_type(section_type)
        
        # Check if we have this extractor cached
        if normalized in self._instances:
            return self._instances[normalized]
        
        # Look up extractor class in registry
        extractor_class = self._registry.get(normalized)
        
        if not extractor_class:
            return None
        
        # Instantiate and cache the extractor
        extractor = extractor_class(
            session=self.session,
            provider=self.provider,
            gemini_api_key=self.gemini_api_key,
            gemini_model=self.gemini_model,
            openrouter_api_key=self.openrouter_api_key,
            openrouter_model=self.openrouter_model,
            openrouter_api_url=self.openrouter_api_url,
        )
        
        self._instances[normalized] = extractor
        return extractor
    
    def _normalize_section_type(self, section_type: str) -> str:
        """Normalize section type for consistent lookup."""
        return section_type.lower().replace("_", " ").strip()
    
    def list_supported_types(self) -> List[str]:
        """List all supported section types."""
        return sorted(self._registry.keys())
