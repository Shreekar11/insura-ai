"""Entity and relationship extraction service.

This service combines entity and relationship extraction into a single LLM call
to optimize API costs and latency. It extracts structured information from
normalized insurance document text.
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from uuid import UUID

from app.core.unified_llm import UnifiedLLMClient
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
    
    # Pass 1: Entity Extraction Only (relationships moved to Pass 2)
    ENTITY_EXTRACTION_PROMPT = """You are an advanced insurance-domain information extraction system designed to convert unstructured insurance document text into structured, graph-ready JSON.

Your task in this phase is **ENTITY EXTRACTION ONLY** (Pass 1 of 2).  
DO NOT infer or output relationships in this phase.

---

# 🎯 OBJECTIVE
Extract all entity mentions present in the document, normalize them, and return metadata suitable for graph construction.

Your output must be:
- **Deterministic**
- **Strictly JSON**
- **Graph-ready**
- **Span-accurate**
- **Confidence-scored**

---

# 📘 ENTITY ONTOLOGY
Extract ONLY the following allowed entity types:

### **Policy / Claim Identifiers**
- POLICY_NUMBER — Alphanumeric policy identifiers (e.g., "POL12345", "Policy No. ABC-4444")
- CLAIM_NUMBER — Loss/claim identifiers

### **Actors / Parties**
- INSURED_NAME — Named insured(s)
- CARRIER — Insurance carrier company
- BROKER — Broker or agent

### **Temporal Entities**
- EFFECTIVE_DATE — Policy binding/coverage start
- EXPIRY_DATE — Policy end date

### **Financial Entities**
- PREMIUM — Total premium amount
- LIMIT — Coverage limit
- DEDUCTIBLE — Deductible

### **Coverage / Structural Entities**
- COVERAGE_TYPE — Example: Property, Liability, Auto, Inland Marine
- ADDRESS — Mailing or risk address
- LOCATION — Building name, suite, property label, etc.

---

# 🧠 EXTRACTION GUIDELINES

### 1. **Span Accuracy**
- span_start and span_end refer to character offsets inside the *exact input text provided to you*.
- Count characters exactly; do not estimate.

### 2. **Normalization Rules**
Apply:
- Trim whitespace  
- Remove special chars from IDs (e.g., "POL-123 456" → "POL123456")  
- Standardize dates to **YYYY-MM-DD**  
- Convert currency to numeric form (e.g., "$1,200.00" → "1200.00")  
- Titles/case retain original (raw_value), normalize only normalized_value  

### 3. **Extraction Strategy**
Perform a 3-step extraction:
1. Scan structurally for well-known patterns (policy numbers, dates, currency)
2. Use semantic understanding for implicit mentions
3. Extract **even partial / incomplete** entities → lower confidence

### 4. **Strict Exclusions**
DO NOT extract:
- Regulation references ("Section 4.2", "AB-123 statute")
- Page numbers
- Headers/footers
- Definitions ("'Policy' means…" unless it contains a real value)
- Boilerplate legal text
- Acronyms alone without clear meaning

### 5. **Confidence Guidelines**
- 0.90–1.00 = Explicitly present, high certainty
- 0.70–0.89 = Present but formatting unclear
- 0.40–0.69 = Partially present or inferred
- 0.10–0.39 = Very weak signal (still allowed)
- Never return < 0.10

---

# 🔎 OUTPUT FORMAT (STRICT)

Return ONLY this JSON structure:
```json
{
  "entities": [
    {
      "entity_id": "string-unique-id",
      "entity_type": "POLICY_NUMBER",
      "raw_value": "Policy No. ABC-4444",
      "normalized_value": "ABC4444",
      "confidence": 0.95,
      "span_start": 123,
      "span_end": 145
    }
  ]
}
```

### **Rules**
- entity_id must be a deterministic hash based on entity_type and normalized_value
- No relationships here (those belong to pass 2)
- No markdown, no explanations, no comments

---

# 🚫 DO NOT
- Do NOT infer relationships
- Do NOT produce multiple JSON blocks
- Do NOT hallucinate entities
- Do NOT output anything besides the JSON

---

# 📝 EXAMPLES

**Example 1: Policy Declaration**
Input Text:
"Policy Number: POL-2024-12345. Insured: ABC Manufacturing LLC. Effective Date: 01/15/2024. Premium: $15,000.00"

Output:
```json
{
  "entities": [
    {
      "entity_id": "policy_number_pol202412345",
      "entity_type": "POLICY_NUMBER",
      "raw_value": "POL-2024-12345",
      "normalized_value": "POL202412345",
      "confidence": 0.98,
      "span_start": 16,
      "span_end": 30
    },
    {
      "entity_id": "insured_name_abc_manufacturing_llc",
      "entity_type": "INSURED_NAME",
      "raw_value": "ABC Manufacturing LLC",
      "normalized_value": "ABC Manufacturing LLC",
      "confidence": 0.95,
      "span_start": 42,
      "span_end": 63
    },
    {
      "entity_id": "effective_date_2024-01-15",
      "entity_type": "EFFECTIVE_DATE",
      "raw_value": "01/15/2024",
      "normalized_value": "2024-01-15",
      "confidence": 0.99,
      "span_start": 82,
      "span_end": 92
    },
    {
      "entity_id": "premium_15000.00",
      "entity_type": "PREMIUM",
      "raw_value": "$15,000.00",
      "normalized_value": "15000.00",
      "confidence": 0.97,
      "span_start": 103,
      "span_end": 113
    }
  ]
}
```

**Example 2: Coverage Section**
Input Text:
"Building Coverage: $5,000,000 limit with $10,000 deductible. Contents Coverage: $1,000,000."

Output:
```json
{
  "entities": [
    {
      "entity_id": "coverage_type_building_coverage",
      "entity_type": "COVERAGE_TYPE",
      "raw_value": "Building Coverage",
      "normalized_value": "Building Coverage",
      "confidence": 0.96,
      "span_start": 0,
      "span_end": 17
    },
    {
      "entity_id": "limit_5000000.00",
      "entity_type": "LIMIT",
      "raw_value": "$5,000,000",
      "normalized_value": "5000000.00",
      "confidence": 0.98,
      "span_start": 19,
      "span_end": 29
    },
    {
      "entity_id": "deductible_10000.00",
      "entity_type": "DEDUCTIBLE",
      "raw_value": "$10,000",
      "normalized_value": "10000.00",
      "confidence": 0.97,
      "span_start": 41,
      "span_end": 48
    },
    {
      "entity_id": "coverage_type_contents_coverage",
      "entity_type": "COVERAGE_TYPE",
      "raw_value": "Contents Coverage",
      "normalized_value": "Contents Coverage",
      "confidence": 0.96,
      "span_start": 62,
      "span_end": 79
    },
    {
      "entity_id": "limit_1000000.00",
      "entity_type": "LIMIT",
      "raw_value": "$1,000,000",
      "normalized_value": "1000000.00",
      "confidence": 0.98,
      "span_start": 81,
      "span_end": 91
    }
  ]
}
```

---

Now extract entities from the following text:

{text}
"""
    
    def __init__(
        self,
        provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "qwen3:8b",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "openai/gpt-oss-20b:free",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        """Initialize entity/relationship extractor.
        
        Args:
            provider: LLM provider to use ("gemini" or "openrouter")
            gemini_api_key: Gemini API key
            gemini_model: Gemini model to use
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model to use
            openrouter_api_url: OpenRouter API URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.provider = provider
        
        # Determine which API key and model to use
        if provider == "openrouter":
            if not openrouter_api_key:
                raise ValueError("openrouter_api_key required when provider='openrouter'")
            api_key = openrouter_api_key
            model = openrouter_model
            base_url = openrouter_api_url
        else:  # gemini
            if not gemini_api_key:
                raise ValueError("gemini_api_key required when provider='gemini'")
            api_key = gemini_api_key
            model = gemini_model
            base_url = None
        
        
        # Store model for external access
        self.model = model
        
        # Initialize UnifiedLLMClient
        self.client = UnifiedLLMClient(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            fallback_to_gemini=False,
        )
        
        LOGGER.info(
            "Initialized entity/relationship extractor",
            extra={
                "model": model,
            }
        )
    
    async def extract(
        self,
        text: str,
        chunk_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Extract entities from text (Pass 1 - entities only).
        
        Note: Relationships are now extracted in Pass 2 (global extraction)
        after entity resolution.
        
        Args:
            text: Normalized text to extract from
            chunk_id: Optional chunk ID for logging
            
        Returns:
            dict: Dictionary with entities only
                {
                    "entities": [...],
                    "relationships": []  # Empty in Pass 1
                }
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for extraction")
            return {"entities": [], "relationships": []}
        
        LOGGER.info(
            "Starting entity extraction (Pass 1)",
            extra={
                "text_length": len(text),
                "chunk_id": str(chunk_id) if chunk_id else None
            }
        )
        
        try:
            result = await self._call_llm_api(text)
            
            # Pass 1 returns only entities, relationships will be empty
            result["relationships"] = []
            
            LOGGER.info(
                "Entity extraction completed successfully",
                extra={
                    "entities_count": len(result.get("entities", [])),
                    "chunk_id": str(chunk_id) if chunk_id else None
                }
            )
            
            return result
            
        except Exception as e:
            LOGGER.error(
                "Entity extraction failed, returning empty result",
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
        try:
            # Use GeminiClient
            llm_response = await self.client.generate_content(
                contents=f"Text:\n{text}",
                system_instruction=self.ENTITY_EXTRACTION_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse JSON response
            return self._parse_extraction_response(llm_response)
            
        except Exception as e:
            LOGGER.error(f"LLM extraction failed: {e}", exc_info=True)
            raise APIClientError(f"Failed to extract entities: {e}")
    
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
