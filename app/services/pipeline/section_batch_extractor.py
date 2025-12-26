"""Section batch extractor for optimized multi-section extraction.

This service processes Conditions, Coverages, and Exclusions sections in a
single LLM call instead of 3 separate calls, reducing API calls by 67% for
section-heavy documents.

Status: Production-ready optimization integrated into the main pipeline.
"""

import json
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base_service import BaseService
from app.core.unified_llm import UnifiedLLMClient, create_llm_client_from_settings
from app.database.models import CoverageItem, ConditionItem, ExclusionItem
from app.utils.exceptions import APIClientError
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


class SectionBatchExtractor(BaseService):
    """Section batch extractor for all section types.
    
    This service processes all detected sections (coverages, conditions,
    exclusions) in a single LLM call, reducing API calls and improving
    consistency across section types.
    
    Attributes:
        session: SQLAlchemy async session
        client: GeminiClient for LLM API calls
    """
    
    UNIFIED_SECTION_PROMPT = """You are an expert at extracting structured information from insurance policy sections.

You will receive text from multiple section types. Extract ALL relevant information for each section type.

## Section Types

### 1. Coverages
Extract coverage information including:
- coverage_name: Name of coverage
- coverage_type: Type/category (Property, Liability, Auto, etc.)
- limit_amount: Coverage limit (numeric)
- deductible_amount: Deductible (numeric)
- premium_amount: Premium (numeric)
- description: What is covered
- sub_limits: Object with sub-limits (e.g., {"theft": 50000})
- exclusions: List of exclusions specific to this coverage
- conditions: List of conditions specific to this coverage
- per_occurrence: Boolean - limit is per occurrence
- aggregate: Boolean - has aggregate limit

### 2. Conditions
Extract policy conditions including:
- condition_type: Type (Coverage Condition, Claim Condition, General Condition)
- title: Brief title
- description: Full description
- applies_to: What it applies to
- requirements: List of requirements
- consequences: What happens if not met
- reference: Section/clause reference

### 3. Exclusions
Extract exclusions including:
- exclusion_type: Type (General Exclusion, Coverage-Specific, etc.)
- title: Brief title
- description: Full description
- applies_to: What it applies to
- exceptions: List of exceptions to the exclusion
- reference: Section/clause reference

## Example Input

```json
{
  "sections": {
    "coverages": [
      "COVERAGE A - BUILDING: Limit $5,000,000, Deductible $5,000, Premium $12,500"
    ],
    "conditions": [
      "DUTIES IN THE EVENT OF LOSS: You must report all claims within 30 days"
    ],
    "exclusions": [
      "We do not cover loss or damage caused by: 1. Wear and tear 2. Intentional acts"
    ]
  }
}
```

## Example Output

```json
{
  "coverages": [
    {
      "coverage_name": "Building Coverage",
      "coverage_type": "Property",
      "limit_amount": 5000000,
      "deductible_amount": 5000,
      "premium_amount": 12500,
      "description": "Covers direct physical loss or damage to buildings",
      "sub_limits": null,
      "exclusions": [],
      "conditions": [],
      "per_occurrence": true,
      "aggregate": false
    }
  ],
  "conditions": [
    {
      "condition_type": "Claim Condition",
      "title": "Duties in the Event of Loss",
      "description": "You must report all claims within 30 days",
      "applies_to": "All Coverages",
      "requirements": ["Report within 30 days"],
      "consequences": "Failure to report may result in denial of claim",
      "reference": null
    }
  ],
  "exclusions": [
    {
      "exclusion_type": "General Exclusion",
      "title": "Wear and Tear",
      "description": "Loss or damage caused by wear and tear or intentional acts",
      "applies_to": "All Coverages",
      "exceptions": [],
      "reference": null
    }
  ]
}
```

## Important Rules
1. Extract ALL items from each section
2. Use null for missing values
3. Numeric values must be numbers, not strings
4. Be comprehensive - don't skip items
5. Return ONLY valid JSON (no code fences)
"""

    def __init__(
        self,
        session: AsyncSession,
        provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "openai/gpt-oss-20b:free",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        ollama_model: str = "deepseek-r1:7b",
        timeout: int = 90,
        max_retries: int = 3,
    ):
        """Initialize section batch extractor.
        
        Args:
            session: SQLAlchemy async session
            provider: LLM provider to use ("gemini", "openrouter", or "ollama")
            gemini_api_key: Gemini API key
            gemini_model: Gemini model to use
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model to use
            openrouter_api_url: OpenRouter API URL
            ollama_model: Ollama model to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        super().__init__(repository=None)
        self.session = session
        self.provider = provider
        
        # Initialize UnifiedLLMClient using factory function
        self.client = create_llm_client_from_settings(
            provider=provider,
            gemini_api_key=gemini_api_key if gemini_api_key else "",
            gemini_model=gemini_model,
            openrouter_api_key=openrouter_api_key if openrouter_api_key else "",
            openrouter_api_url=openrouter_api_url,
            openrouter_model=openrouter_model,
            ollama_api_url="http://localhost:11434",
            ollama_model="deepseek-r1:7b",
            timeout=timeout,
            max_retries=max_retries,
            enable_fallback=False,
        )
        
        # Store model for external access
        self.model = self.client.model
        
        LOGGER.info(f"Initialized SectionBatchExtractor with provider={provider}, model={self.model}")
    
    async def extract_all_sections(
        self,
        sections: Dict[str, List[str]],
        document_id: UUID
    ) -> Dict[str, List[Any]]:
        """Extract all section types in a single LLM call.
        
        Args:
            sections: Dictionary mapping section types to text chunks
                     e.g., {"coverages": ["text1", "text2"], "conditions": [...]}
            document_id: Document UUID
            
        Returns:
            Dictionary with extracted items for each section type:
            {
                "coverages": [CoverageItem, ...],
                "conditions": [ConditionItem, ...],
                "exclusions": [ExclusionItem, ...]
            }
        """
        if not sections:
            LOGGER.warning("No sections provided for extraction")
            return {"coverages": [], "conditions": [], "exclusions": []}
        
        LOGGER.info(
            f"Starting unified section extraction for {len(sections)} section types",
            extra={
                "document_id": str(document_id),
                "section_types": list(sections.keys())
            }
        )
        
        try:
            # Call LLM API
            extraction_results = await self._call_llm_api(sections)
            
            # Create database records
            db_results = await self._create_db_records(
                extraction_results,
                document_id
            )
            
            LOGGER.info(
                f"Unified section extraction completed",
                extra={
                    "document_id": str(document_id),
                    "coverages": len(db_results.get("coverages", [])),
                    "conditions": len(db_results.get("conditions", [])),
                    "exclusions": len(db_results.get("exclusions", []))
                }
            )
            
            return db_results
            
        except Exception as e:
            LOGGER.error(
                f"Unified section extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return {"coverages": [], "conditions": [], "exclusions": []}
    
    async def run(
        self,
        sections: Dict[str, List[str]],
        document_id: UUID
    ) -> Dict[str, List[Any]]:
        """Execute section extraction (BaseService compatibility).
        
        Args:
            sections: Section text dictionary
            document_id: Document UUID
            
        Returns:
            Extraction results
        """
        return await self.extract_all_sections(sections, document_id)
    
    async def _call_llm_api(
        self,
        sections: Dict[str, List[str]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Call LLM API for section extraction.
        
        Args:
            sections: Section text dictionary
            
        Returns:
            Parsed extraction results
        """
        # Prepare input
        section_input = {
            "sections": {
                section_type: texts
                for section_type, texts in sections.items()
            }
        }
        
        input_json = json.dumps(section_input, indent=2)
        
        LOGGER.debug(
            f"Calling LLM API for {len(sections)} section types",
            extra={"section_types": list(sections.keys())}
        )
        
        try:
            # Call Gemini API
            llm_response = await self.client.generate_content(
                contents=f"Extract structured data from these sections:\n\n{input_json}",
                system_instruction=self.UNIFIED_SECTION_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse response
            parsed = self._parse_response(llm_response)
            
            return parsed
            
        except Exception as e:
            LOGGER.error(f"LLM API call failed: {e}", exc_info=True)
            raise APIClientError(f"Unified section extraction API call failed: {e}")
    
    def _parse_response(self, response_text: str) -> Dict[str, List[Dict[str, Any]]]:
        """Parse and validate LLM response.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            Parsed response dictionary
        """
        parsed = parse_json_safely(response_text)
        
        if parsed is None:
            LOGGER.error("Failed to parse LLM response as JSON")
            return {"coverages": [], "conditions": [], "exclusions": []}
        
        if not isinstance(parsed, dict):
            LOGGER.warning("LLM response is not a dictionary")
            return {"coverages": [], "conditions": [], "exclusions": []}
        
        # Ensure all section types are present
        result = {
            "coverages": parsed.get("coverages", []),
            "conditions": parsed.get("conditions", []),
            "exclusions": parsed.get("exclusions", [])
        }
        
        return result
    
    async def _create_db_records(
        self,
        extraction_results: Dict[str, List[Dict[str, Any]]],
        document_id: UUID
    ) -> Dict[str, List[Any]]:
        """Create database records from extraction results.
        
        Args:
            extraction_results: Parsed extraction results
            document_id: Document UUID
            
        Returns:
            Dictionary of created database records
        """
        db_results = {
            "coverages": [],
            "conditions": [],
            "exclusions": []
        }
        
        # Create coverage records
        for coverage_data in extraction_results.get("coverages", []):
            try:
                coverage = await self._create_coverage(coverage_data, document_id)
                db_results["coverages"].append(coverage)
            except Exception as e:
                LOGGER.error(f"Failed to create coverage record: {e}", exc_info=True)
        
        # Create condition records
        for condition_data in extraction_results.get("conditions", []):
            try:
                condition = await self._create_condition(condition_data, document_id)
                db_results["conditions"].append(condition)
            except Exception as e:
                LOGGER.error(f"Failed to create condition record: {e}", exc_info=True)
        
        # Create exclusion records
        for exclusion_data in extraction_results.get("exclusions", []):
            try:
                exclusion = await self._create_exclusion(exclusion_data, document_id)
                db_results["exclusions"].append(exclusion)
            except Exception as e:
                LOGGER.error(f"Failed to create exclusion record: {e}", exc_info=True)
        
        return db_results
    
    async def _create_coverage(
        self,
        data: Dict[str, Any],
        document_id: UUID
    ) -> CoverageItem:
        """Create CoverageItem record."""
        from decimal import Decimal
        
        coverage = CoverageItem(
            document_id=document_id,
            chunk_id=None,  # Document-level extraction
            coverage_name=data.get("coverage_name"),
            coverage_type=data.get("coverage_type"),
            limit_amount=Decimal(str(data["limit_amount"])) if data.get("limit_amount") else None,
            deductible_amount=Decimal(str(data["deductible_amount"])) if data.get("deductible_amount") else None,
            premium_amount=Decimal(str(data["premium_amount"])) if data.get("premium_amount") else None,
            description=data.get("description"),
            sub_limits=data.get("sub_limits"),
            exclusions=data.get("exclusions"),
            conditions=data.get("conditions"),
            per_occurrence=data.get("per_occurrence"),
            aggregate=data.get("aggregate"),
            additional_data=data
        )
        
        self.session.add(coverage)
        await self.session.flush()
        
        return coverage
    
    async def _create_condition(
        self,
        data: Dict[str, Any],
        document_id: UUID
    ) -> ConditionItem:
        """Create ConditionItem record."""
        condition = ConditionItem(
            document_id=document_id,
            chunk_id=None,  # Document-level extraction
            condition_type=data.get("condition_type"),
            title=data.get("title"),
            description=data.get("description"),
            applies_to=data.get("applies_to"),
            requirements=data.get("requirements"),
            consequences=data.get("consequences"),
            reference=data.get("reference"),
            additional_data=data
        )
        
        self.session.add(condition)
        await self.session.flush()
        
        return condition
    
    async def _create_exclusion(
        self,
        data: Dict[str, Any],
        document_id: UUID
    ) -> ExclusionItem:
        """Create ExclusionItem record."""
        exclusion = ExclusionItem(
            document_id=document_id,
            chunk_id=None,  # Document-level extraction
            exclusion_type=data.get("exclusion_type"),
            title=data.get("title"),
            description=data.get("description"),
            applies_to=data.get("applies_to"),
            exceptions=data.get("exceptions"),
            reference=data.get("reference"),
            additional_data=data
        )
        
        self.session.add(exclusion)
        await self.session.flush()
        
        return exclusion
