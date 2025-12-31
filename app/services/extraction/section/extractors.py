"""Section-specific extractors for different section types.

This module contains extractor classes for each section type, each implementing
the BaseExtractor interface with section-specific prompts and extraction logic.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from click import Option
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extraction.base_extractor import BaseExtractor
from app.services.chunking.hybrid_models import SectionType
from app.utils.logging import get_logger
from app.prompts.system_prompts import (
    DECLARATIONS_EXTRACTION_PROMPT,
    DEFINITIONS_EXTRACTION_PROMPT,
    COVERAGES_EXTRACTION_PROMPT,
    CONDITIONS_EXTRACTION_PROMPT,
    EXCLUSIONS_EXTRACTION_PROMPT,
    ENDORSEMENTS_EXTRACTION_PROMPT,
    INSURING_AGREEMENT_EXTRACTION_PROMPT,
    PREMIUM_SUMMARY_EXTRACTION_PROMPT,
    DEFAULT_SECTION_EXTRACTION_PROMPT,
)

LOGGER = get_logger(__name__)


class DeclarationsExtractor(BaseExtractor):
    """Extractor for declarations section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for declarations."""
        return DECLARATIONS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract declarations data from text."""
        # Use direct LLM call for section extraction
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this declarations section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Declarations extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return parsed.get("fields", parsed)

class DefinitionsExtractor(BaseExtractor):
    """Extractor for definitions section."""

    def get_extraction_prompt(self) -> str:
        return DEFINITIONS_EXTRACTION_PROMPT

    async def run(self, text: str, document_id: UUID, chunk_id: Optional[UUID] = None) -> List[Any]:
        """Extract definitions data from text"""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this definitions sections: \n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Definitions extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return {
            "definitions": parsed.get("definitions", []),
            "entities": parsed.get("entities", []),
        }

class CoveragesExtractor(BaseExtractor):
    """Extractor for coverages section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for coverages."""
        return COVERAGES_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract coverages data from text."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this coverages section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Coverages extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return {"coverages": parsed.get("coverages", [])}


class ConditionsExtractor(BaseExtractor):
    """Extractor for conditions section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for conditions."""
        return CONDITIONS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract conditions data from text."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this conditions section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Conditions extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return {"conditions": parsed.get("conditions", [])}


class ExclusionsExtractor(BaseExtractor):
    """Extractor for exclusions section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for exclusions."""
        return EXCLUSIONS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract exclusions data from text."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this exclusions section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Exclusions extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return {"exclusions": parsed.get("exclusions", [])}


class EndorsementsExtractor(BaseExtractor):
    """Extractor for endorsements section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for endorsements."""
        return ENDORSEMENTS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract endorsements data from text."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this endorsements section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Endorsements extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return {"endorsements": parsed.get("endorsements", [])}


class InsuringAgreementExtractor(BaseExtractor):
    """Extractor for insuring agreement section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for insuring agreement."""
        return INSURING_AGREEMENT_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract insuring agreement data from text."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this insuring agreement section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Insuring agreement extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return parsed.get("insuring_agreement", parsed)


class PremiumSummaryExtractor(BaseExtractor):
    """Extractor for premium summary section."""
    
    def get_extraction_prompt(self) -> str:
        """Get the extraction prompt for premium summary."""
        return PREMIUM_SUMMARY_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract premium summary data from text."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this premium summary section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Premium summary extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return parsed.get("premium", parsed)


class DefaultSectionExtractor(BaseExtractor):
    """Default extractor for unknown section types."""
    
    def get_extraction_prompt(self) -> str:
        """Get the default extraction prompt."""
        return DEFAULT_SECTION_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[Any]:
        """Extract data from text using default prompt."""
        try:
            response = await self.client.generate_content(
                contents=f"Extract from this section:\n\n{text}",
                system_instruction=self.get_extraction_prompt(),
                generation_config={"response_mime_type": "application/json"}
            )
            from app.utils.json_parser import parse_json_safely
            parsed = parse_json_safely(response)
            return [parsed] if parsed else []
        except Exception as e:
            LOGGER.error(f"Default section extraction failed: {e}", exc_info=True)
            return []
    
    def extract_fields(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Extract fields from parsed response."""
        return parsed.get("extracted_data", parsed)

