"""Entity and relationship extraction service.

This service combines entity and relationship extraction into a single LLM call
to optimize API costs and latency. It extracts structured information from
normalized insurance document text.
"""

import httpx
import json
import asyncio
from typing import Dict, List, Any, Optional
from uuid import UUID

from app.utils.exceptions import APIClientError, OCRTimeoutError
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Valid entity types (from Neo4j ontology)
VALID_ENTITY_TYPES = {
    "POLICY_NUMBER",
    "CLAIM_NUMBER",
    "INSURED_NAME",
    "ADDRESS",
    "COVERAGE_TYPE",
    "LIMIT",
    "DEDUCTIBLE",
    "EFFECTIVE_DATE",
    "EXPIRY_DATE",
    "CARRIER",
    "BROKER",
    "PREMIUM",
    "LOCATION",
}

# Valid relationship types (from Neo4j ontology)
VALID_RELATIONSHIP_TYPES = {
    "HAS_INSURED",
    "HAS_COVERAGE",
    "HAS_LIMIT",
    "HAS_DEDUCTIBLE",
    "HAS_CLAIM",
    "LOCATED_AT",
    "EFFECTIVE_FROM",
    "EXPIRES_ON",
    "ISSUED_BY",
    "BROKERED_BY",
}


class EntityRelationshipExtractor:
    """Combined entity and relationship extraction service.
    
    This service uses a single LLM call to extract both entities and their
    relationships from normalized text, reducing API costs and latency.
    
    Attributes:
        openrouter_api_key: OpenRouter API key
        openrouter_api_url: OpenRouter API URL
        openrouter_model: Model to use for extraction
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
    """
    
    # Combined extraction prompt
    EXTRACTION_PROMPT = """You are an expert at extracting structured information from insurance documents.

Analyze the following insurance document text and extract:
1. All entities (policy numbers, names, dates, amounts, etc.)
2. Relationships between those entities

**Entity Types:**
- POLICY_NUMBER: Policy identification number
- CLAIM_NUMBER: Claim identification number
- INSURED_NAME: Name of insured party
- ADDRESS: Physical address
- COVERAGE_TYPE: Type of coverage (e.g., Property, Liability, Auto)
- LIMIT: Coverage limit amount
- DEDUCTIBLE: Deductible amount
- EFFECTIVE_DATE: Policy effective date
- EXPIRY_DATE: Policy expiration date
- CARRIER: Insurance carrier/company name
- BROKER: Insurance broker/agent name
- PREMIUM: Premium amount
- LOCATION: Property location or building name

**Relationship Types:**
- HAS_INSURED: Policy has insured party
- HAS_COVERAGE: Policy has coverage type
- HAS_LIMIT: Coverage has limit amount
- HAS_DEDUCTIBLE: Coverage has deductible
- HAS_CLAIM: Policy has claim
- LOCATED_AT: Entity located at address
- EFFECTIVE_FROM: Policy effective from date
- EXPIRES_ON: Policy expires on date
- ISSUED_BY: Policy issued by carrier
- BROKERED_BY: Policy brokered by broker

**Instructions:**
1. Extract all entities with their exact text spans
2. Normalize entity values (e.g., remove spaces from policy numbers, standardize dates to YYYY-MM-DD)
3. Identify relationships between entities
4. Provide confidence scores (0.0-1.0) for each extraction

**Return ONLY valid JSON** with this exact structure (no code fences, no explanations):
{
  "entities": [
    {
      "entity_type": "POLICY_NUMBER",
      "raw_value": "POL-123-456",
      "normalized_value": "POL123456",
      "confidence": 0.95,
      "span_start": 10,
      "span_end": 21
    }
  ],
  "relationships": [
    {
      "type": "HAS_INSURED",
      "source_type": "POLICY_NUMBER",
      "source_value": "POL123456",
      "target_type": "INSURED_NAME",
      "target_value": "John Doe",
      "confidence": 0.90
    }
  ]
}

**Important:**
- Only extract entities that are actually present in the text
- Provide accurate span positions for entities
- Ensure all JSON is properly escaped
- Use normalized values for relationship references
"""
    
    def __init__(
        self,
        openrouter_api_key: str,
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        openrouter_model: str = "google/gemini-2.0-flash-001",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """Initialize entity/relationship extractor.
        
        Args:
            openrouter_api_key: OpenRouter API key
            openrouter_api_url: OpenRouter API URL
            openrouter_model: Model to use for extraction
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_api_url = openrouter_api_url
        self.openrouter_model = openrouter_model
        self.timeout = timeout
        self.max_retries = max_retries
        
        LOGGER.info(
            "Initialized entity/relationship extractor",
            extra={
                "model": self.openrouter_model,
                "api_url": self.openrouter_api_url,
            }
        )
    
    async def extract(
        self,
        text: str,
        chunk_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Extract entities and relationships from text.
        
        Args:
            text: Normalized text to extract from
            chunk_id: Optional chunk ID for logging
            
        Returns:
            dict: Dictionary with entities and relationships
                {
                    "entities": [...],
                    "relationships": [...]
                }
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for extraction")
            return {"entities": [], "relationships": []}
        
        LOGGER.info(
            "Starting entity/relationship extraction",
            extra={
                "text_length": len(text),
                "chunk_id": str(chunk_id) if chunk_id else None
            }
        )
        
        try:
            result = await self._call_llm_api(text)
            
            LOGGER.info(
                "Extraction completed successfully",
                extra={
                    "entities_count": len(result.get("entities", [])),
                    "relationships_count": len(result.get("relationships", [])),
                    "chunk_id": str(chunk_id) if chunk_id else None
                }
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(
                "Extraction failed, returning empty result",
                exc_info=True,
                extra={"error": str(e), "chunk_id": str(chunk_id) if chunk_id else None}
            )
            return {"entities": [], "relationships": []}
    
    async def _call_llm_api(self, text: str) -> Dict[str, Any]:
        """Call LLM API for extraction.
        
        Args:
            text: Text to extract from
            
        Returns:
            dict: Parsed extraction result
            
        Raises:
            APIClientError: If API call fails after retries
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
                    "content": self.EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Text:\n{text}"
                }
            ],
            "temperature": 0.0,  # Deterministic output
            "max_tokens": 4000,  # Allow for structured output
        }
        
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
                    llm_response = result["choices"][0]["message"]["content"].strip()
                    
                    # Parse JSON response
                    parsed = self._parse_extraction_response(llm_response)
                    
                    return parsed
                    
                except httpx.HTTPStatusError as e:
                    # Server errors (5xx) - retry with exponential backoff
                    if e.response.status_code >= 500:
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                            LOGGER.warning(
                                f"LLM server error {e.response.status_code}, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})",
                                extra={"status_code": e.response.status_code}
                            )
                            await asyncio.sleep(wait_time)
                            continue
                    
                    # Client errors (4xx) - don't retry, or if max retries reached for 5xx
                    LOGGER.error(
                        f"LLM API error: {e.response.status_code}",
                        exc_info=True,
                        extra={"status_code": e.response.status_code}
                    )
                    raise APIClientError(f"API returned error: {e.response.status_code}") from e
                    
                except httpx.TimeoutException as e:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        LOGGER.warning(
                            f"LLM timeout, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    raise OCRTimeoutError("API call timed out") from e
                    
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        LOGGER.warning(
                            f"Unexpected error, retrying in {wait_time}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    raise
        
        raise APIClientError("Failed to extract after all retry attempts")
    
    def _parse_extraction_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate extraction response.
        
        Args:
            response_text: Raw LLM response
            
        Returns:
            dict: Validated extraction result
        """
        try:
            # Clean response - remove markdown code fences
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
            
            # Validate structure
            if "entities" not in parsed:
                parsed["entities"] = []
            if "relationships" not in parsed:
                parsed["relationships"] = []
            
            # Validate entities
            validated_entities = []
            for entity in parsed.get("entities", []):
                if self._validate_entity(entity):
                    validated_entities.append(entity)
            
            # Validate relationships
            validated_relationships = []
            for rel in parsed.get("relationships", []):
                if self._validate_relationship(rel):
                    validated_relationships.append(rel)
            
            return {
                "entities": validated_entities,
                "relationships": validated_relationships
            }
            
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse JSON: {e}")
            LOGGER.debug(f"Raw response: {response_text[:500]}...")
            return {"entities": [], "relationships": []}
        except Exception as e:
            LOGGER.error(f"Unexpected error parsing response: {e}")
            return {"entities": [], "relationships": []}
    
    def _validate_entity(self, entity: dict) -> bool:
        """Validate entity structure and type.
        
        Args:
            entity: Entity dict to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        required_fields = ["entity_type", "raw_value", "normalized_value", "confidence"]
        
        # Check required fields
        if not all(field in entity for field in required_fields):
            LOGGER.warning(
                "Entity missing required fields",
                extra={
                    "entity": entity,
                    "missing_fields": [f for f in required_fields if f not in entity]
                }
            )
            return False
        
        # Check entity type
        if entity["entity_type"] not in VALID_ENTITY_TYPES:
            LOGGER.warning(
                "Invalid entity type",
                extra={
                    "entity_type": entity["entity_type"],
                    "valid_types": list(VALID_ENTITY_TYPES)
                }
            )
            return False
        
        # Check confidence range
        try:
            confidence = float(entity["confidence"])
            if not (0.0 <= confidence <= 1.0):
                LOGGER.warning(
                    "Invalid confidence value",
                    extra={"confidence": confidence, "entity_type": entity["entity_type"]}
                )
                return False
        except (ValueError, TypeError):
            LOGGER.warning(
                "Invalid confidence format",
                extra={"confidence": entity.get("confidence"), "entity_type": entity["entity_type"]}
            )
            return False
        
        # Check that values are non-empty strings
        if not isinstance(entity["raw_value"], str) or not entity["raw_value"].strip():
            LOGGER.warning(
                "Invalid raw_value",
                extra={"raw_value": entity.get("raw_value"), "entity_type": entity["entity_type"]}
            )
            return False
            
        if not isinstance(entity["normalized_value"], str) or not entity["normalized_value"].strip():
            LOGGER.warning(
                "Invalid normalized_value",
                extra={"normalized_value": entity.get("normalized_value"), "entity_type": entity["entity_type"]}
            )
            return False
        
        return True
    
    def _validate_relationship(self, relationship: dict) -> bool:
        """Validate relationship structure and type.
        
        Args:
            relationship: Relationship dict to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        required_fields = ["type", "source_type", "source_value", "target_type", "target_value", "confidence"]
        
        # Check required fields
        if not all(field in relationship for field in required_fields):
            LOGGER.warning(
                "Relationship missing required fields",
                extra={
                    "relationship": relationship,
                    "missing_fields": [f for f in required_fields if f not in relationship]
                }
            )
            return False
        
        # Check relationship type
        if relationship["type"] not in VALID_RELATIONSHIP_TYPES:
            LOGGER.warning(
                "Invalid relationship type",
                extra={
                    "relationship_type": relationship["type"],
                    "valid_types": list(VALID_RELATIONSHIP_TYPES)
                }
            )
            return False
        
        # Check source entity type
        if relationship["source_type"] not in VALID_ENTITY_TYPES:
            LOGGER.warning(
                "Invalid source entity type",
                extra={
                    "source_type": relationship["source_type"],
                    "relationship_type": relationship["type"]
                }
            )
            return False
        
        # Check target entity type
        if relationship["target_type"] not in VALID_ENTITY_TYPES:
            LOGGER.warning(
                "Invalid target entity type",
                extra={
                    "target_type": relationship["target_type"],
                    "relationship_type": relationship["type"]
                }
            )
            return False
        
        # Check confidence range
        try:
            confidence = float(relationship["confidence"])
            if not (0.0 <= confidence <= 1.0):
                LOGGER.warning(
                    "Invalid confidence value",
                    extra={"confidence": confidence, "relationship_type": relationship["type"]}
                )
                return False
        except (ValueError, TypeError):
            LOGGER.warning(
                "Invalid confidence format",
                extra={"confidence": relationship.get("confidence"), "relationship_type": relationship["type"]}
            )
            return False
        
        # Check that values are non-empty strings
        if not isinstance(relationship["source_value"], str) or not relationship["source_value"].strip():
            LOGGER.warning(
                "Invalid source_value",
                extra={"source_value": relationship.get("source_value"), "relationship_type": relationship["type"]}
            )
            return False
            
        if not isinstance(relationship["target_value"], str) or not relationship["target_value"].strip():
            LOGGER.warning(
                "Invalid target_value",
                extra={"target_value": relationship.get("target_value"), "relationship_type": relationship["type"]}
            )
            return False
        
        return True
