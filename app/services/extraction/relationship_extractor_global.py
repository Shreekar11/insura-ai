"""Global relationship extractor service (Pass 2).

This service extracts relationships between entities using full document context
after canonical entity resolution. This is Pass 2 of the two-pass extraction strategy.
"""

from app.core.gemini_client import GeminiClient
import json
import asyncio
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    CanonicalEntity,
    NormalizedChunk,
    EntityRelationship,
    Document
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Valid relationship types
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


class RelationshipExtractorGlobal:
    """Extracts relationships using global document context (Pass 2).
    
    This service:
    1. Gathers canonical entities for a document
    2. Builds global context from all chunks
    3. Calls LLM with Pass 2 prompt
    4. Extracts relationships between canonical entities
    5. Persists to entity_relationships table
    
    Attributes:
        session: Database session
        openrouter_api_key: OpenRouter API key
        openrouter_api_url: OpenRouter API URL
        openrouter_model: Model to use
        timeout: Request timeout
        max_retries: Maximum retry attempts
    """
    
    RELATIONSHIP_EXTRACTION_PROMPT = """
    You are an advanced global relationship extraction system used in insurance document pipelines.

This is **PASS 2**, which means:
- All chunks have already been normalized.
- All entities have already been extracted.
- All canonical entities have been resolved (deduplicated).
- Your ONLY job is **document-level relationship inference** across chunks.

You must produce:
- Deterministic output  
- Strict JSON  
- Graph-ready canonical-level relationships  
- Evidence with character spans  
- No hallucinations  
- No commentary outside JSON  

======================================================================
INPUT PROVIDED TO YOU
======================================================================

You will receive:

1. `document_id`
2. `document_type` (policy, claim, SOV, invoice, endorsement, etc.)
3. `canonical_entities`  
   - Already deduplicated  
   - Each has:  
     - `canonical_id`
     - `entity_type`
     - `normalized_value`
     - `aliases` (optional)
4. `chunks`  
   Each chunk has:
   - `chunk_id`
   - `section_type`
   - `page_number`
   - `normalized_text`
5. `DOCUMENT_URL` (for audit trace)
6. `aggregation_metadata` (optional classification signals)

You must use ONLY this information.  
Do NOT invent data or refer to anything not contained in these inputs.

======================================================================
RELATIONSHIP ONTOLOGY (Allowed Types)
======================================================================

You may extract ONLY the following relationships:

### Policy Relationships
- HAS_INSURED
- HAS_COVERAGE
- HAS_LIMIT
- HAS_DEDUCTIBLE
- EFFECTIVE_FROM
- EXPIRES_ON
- ISSUED_BY
- BROKERED_BY

### Claim Relationships
- HAS_CLAIM

### Location Relationships
- LOCATED_AT

No other relationship types are permitted.

======================================================================
RULES & CONSTRAINTS (MUST FOLLOW)
======================================================================

### 🔒 1. ZERO HALLUCINATION
If there is no clear evidence, NO relationship may be created.

### 🧠 2. MUST USE CANONICAL ENTITIES
All relationships must be between:
`source_canonical_id`  
and  
`target_canonical_id`.

If an entity is mentioned in text but does NOT map to a canonical entity →  
Return a **candidate** entry (not a final relationship).

### 🔍 3. EVIDENCE IS MANDATORY
Each relationship MUST include evidence:

- `chunk_id`
- `span_start`
- `span_end`
- `quote` — the exact substring from the chunk text

Relationships **without evidence MUST NOT be produced.**

### 📏 4. CONFIDENCE SCORING
Use the following scale:

| Confidence | Meaning |
|-----------|---------|
| 0.90–1.00 | Explicit statement |
| 0.70–0.89 | Strong implicit context |
| 0.45–0.69 | Weak inference (should be a candidate, not final) |
| < 0.45 | Do not output even as a candidate |

### 🧭 5. SECTION-AWARE BOOSTING
If evidence is in these sections:

- `"declarations"` → boost policy relationships by +0.10
- `"coverage"` → boost HAS_COVERAGE, HAS_LIMIT, HAS_DEDUCTIBLE by +0.10
- `"loss_run"` or `"claim"` → boost HAS_CLAIM by +0.10
- `"sov"` → boost LOCATED_AT & HAS_LIMIT by +0.10

Do not exceed confidence 0.99.

### 🔁 6. MERGE DUPLICATE RELATIONSHIPS
If the same relationship appears across multiple chunks:
- Merge into one relationship
- Add multiple evidence items

### 🚫 7. IGNORED TEXT
Do NOT use the following as evidence:
- Page numbers  
- Headers/footers  
- Table of contents  
- Regulatory footnotes  
- Legal boilerplate  

======================================================================
OUTPUT FORMAT (STRICT JSON ONLY)
======================================================================

Output EXACTLY this structure:

{
  "document_id": "string",
  "document_url": "string",
  "relationships": [
    {
      "relationship_id": "sha1(type + sourceCanonicalId + targetCanonicalId + document_id)",
      "type": "ISSUED_BY",
      "source_canonical_id": "c1",
      "target_canonical_id": "c7",
      "confidence": 0.92,
      "evidence": [
        {
          "chunk_id": "ch-1",
          "span_start": 120,
          "span_end": 180,
          "quote": "Policy No. POL12345 issued by SBI GENERAL INSURANCE COMPANY LIMITED"
        }
      ]
    }
  ],
  "candidates": [
    {
      "candidate_id": "sha1(...)",
      "type": "HAS_INSURED",
      "source_mention": {
        "chunk_id": "ch-2",
        "span_start": 10,
        "span_end": 20,
        "quote": "POL12345"
      },
      "target_mention": {
        "chunk_id": "ch-7",
        "span_start": 5,
        "span_end": 30,
        "quote": "John D."
      },
      "reason": "Insufficient linking phrase",
      "confidence": 0.43
    }
  ],
  "stats": {
    "relationships_found": 3,
    "candidates_returned": 1,
    "time_ms": 1234
  }
}

NO other text is allowed in output.

======================================================================
FEW-SHOT EXAMPLES
======================================================================

### 🧩 Example 1 — Explicit same-chunk match

Chunk:
"Policy Number: POL12345 issued by SBI General Insurance Company Limited."

→ Output:

- Relationship: ISSUED_BY  
- Evidence = exact substring from chunk  
- confidence = 0.95 (explicit)  
- canonical_id mapping required  

---

### 🧩 Example 2 — Cross-chunk relationship

Chunk A:
"Policy No: POL12345"

Chunk B:
"Carrier: SBI General Insurance Company Limited"

Chunk C:
"This policy is issued by SBI General"

→ Relationship:
ISSUED_BY with 3 evidence entries  
Confidence: 0.88 (cross-chunk but strong)

---

### 🧩 Example 3 — Weak evidence → candidate only

Chunk A:
"POL12345"
Chunk B:
"John Doe"

No explicit linking phrases like “insured”, “policyholder”, etc.

→ Return as candidate only  
Confidence: ~0.40  

---

### 🧩 Example 4 — Section boost

Chunk (section: declarations):
"Effective date: Jan 1 2024"

→ Relationship:
EFFECTIVE_FROM

Confidence = base 0.85 → +0.10 boost = 0.95

---

======================================================================
FINAL INSTRUCTION
======================================================================

Now perform **global cross-chunk relationship extraction** using all provided inputs.

Return JSON ONLY.  
No comments, no markdown, no prose.
"""
    
    def __init__(
        self,
        session: AsyncSession,
        gemini_api_key: str,
        gemini_model: str = "gemini-2.0-flash",
        timeout: int = 90,
        max_retries: int = 3,
        openrouter_api_url: str = None, # Deprecated
    ):
        """Initialize global relationship extractor.
        
        Args:
            session: Database session
            gemini_api_key: Gemini API key
            gemini_model: Model to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.session = session
        self.gemini_model = gemini_model
        
        # Initialize GeminiClient
        self.client = GeminiClient(
            api_key=gemini_api_key,
            model=gemini_model,
            timeout=timeout,
            max_retries=max_retries
        )
        
        LOGGER.info(
            "Initialized RelationshipExtractorGlobal",
            extra={"model": self.gemini_model}
        )
    
    async def extract_relationships(
        self,
        document_id: UUID
    ) -> List[EntityRelationship]:
        """Extract relationships for a document using global context.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of created EntityRelationship records
        """
        LOGGER.info(
            f"Starting global relationship extraction",
            extra={"document_id": str(document_id)}
        )
        
        # Gather canonical entities
        canonical_entities = await self._fetch_canonical_entities(document_id)
        
        if not canonical_entities:
            LOGGER.warning(
                f"No canonical entities found for document",
                extra={"document_id": str(document_id)}
            )
            return []
        
        # Fetch document and chunks
        document = await self._fetch_document(document_id)
        chunks = await self._fetch_normalized_chunks(document_id)
        
        if not chunks:
            LOGGER.warning(
                f"No normalized chunks found for document",
                extra={"document_id": str(document_id)}
            )
            return []
        
        # Build global context
        context = self._build_global_context(
            document=document,
            canonical_entities=canonical_entities,
            chunks=chunks
        )
        
        # Call LLM for relationship extraction
        try:
            relationships_data = await self._call_llm_api(context)
            
            # Create EntityRelationship records
            relationships = []
            for rel_data in relationships_data:
                relationship = await self._create_relationship(
                    document_id=document_id,
                    relationship_data=rel_data,
                    canonical_entities=canonical_entities
                )
                if relationship:
                    relationships.append(relationship)
            
            await self.session.flush()
            
            LOGGER.info(
                f"Global relationship extraction completed",
                extra={
                    "document_id": str(document_id),
                    "relationships_extracted": len(relationships)
                }
            )
            
            return relationships
            
        except Exception as e:
            LOGGER.error(
                f"Global relationship extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _fetch_canonical_entities(
        self,
        document_id: UUID
    ) -> List[CanonicalEntity]:
        """Fetch canonical entities for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of canonical entities
        """
        # Get all chunk IDs for this document
        stmt = select(NormalizedChunk.id).join(
            NormalizedChunk.chunk
        ).where(
            NormalizedChunk.chunk.has(document_id=document_id)
        )
        result = await self.session.execute(stmt)
        chunk_ids = [row[0] for row in result.all()]
        
        if not chunk_ids:
            return []
        
        # Get canonical entities linked to these chunks
        from app.database.models import ChunkEntityLink
        
        stmt = select(CanonicalEntity).join(
            ChunkEntityLink,
            ChunkEntityLink.canonical_entity_id == CanonicalEntity.id
        ).where(
            ChunkEntityLink.chunk_id.in_(chunk_ids)
        ).distinct()
        
        result = await self.session.execute(stmt)
        entities = result.scalars().all()
        
        LOGGER.debug(
            f"Fetched {len(entities)} canonical entities",
            extra={"document_id": str(document_id)}
        )
        
        return list(entities)
    
    async def _fetch_document(self, document_id: UUID) -> Optional[Document]:
        """Fetch document record with classifications eagerly loaded.
        
        Args:
            document_id: Document ID
            
        Returns:
            Document record or None
        """
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.classifications))  # Eagerly load to avoid lazy loading
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _fetch_normalized_chunks(
        self,
        document_id: UUID
    ) -> List[NormalizedChunk]:
        """Fetch normalized chunks for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of normalized chunks
        """
        from app.database.models import DocumentChunk
        from sqlalchemy.orm import selectinload
        
        stmt = (
            select(NormalizedChunk)
            .join(NormalizedChunk.chunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .options(selectinload(NormalizedChunk.chunk))  # Eagerly load the relationship
        )
        
        result = await self.session.execute(stmt)
        chunks = result.scalars().all()
        
        return list(chunks)
    
    def _build_global_context(
        self,
        document: Optional[Document],
        canonical_entities: List[CanonicalEntity],
        chunks: List[NormalizedChunk]
    ) -> Dict[str, Any]:
        """Build global context for LLM.
        
        Args:
            document: Document record
            canonical_entities: List of canonical entities
            chunks: List of normalized chunks
            
        Returns:
            Context dictionary
        """
        # Build entities JSON
        entities_list = []
        for entity in canonical_entities:
            # Extract value from attributes JSONB field
            value = entity.attributes.get("normalized_value", "") if entity.attributes else ""
            confidence = entity.attributes.get("confidence", 0.9) if entity.attributes else 0.9
            
            entities_list.append({
                "entity_id": entity.canonical_key,  # Use canonical_key as entity_id
                "entity_type": entity.entity_type,
                "value": value,
                "confidence": confidence
            })
        
        # Build chunks by section
        chunks_by_section = {}
        for chunk in chunks:
            section_type = chunk.chunk.section_type if chunk.chunk else "Unknown"
            if not section_type:
                section_type = "Unknown"
            if section_type not in chunks_by_section:
                chunks_by_section[section_type] = []
            chunks_by_section[section_type].append(chunk.normalized_text or chunk.chunk.raw_text)
        
        # Format chunks for prompt
        chunks_text = ""
        for section, texts in chunks_by_section.items():
            chunks_text += f"\n### Section: {section}\n"
            chunks_text += "\n".join(texts)
            chunks_text += "\n"
        
        return {
            "document_type": document.classifications[0].classified_type if document and document.classifications else "unknown",
            "section_types": list(chunks_by_section.keys()),
            "entities_json": json.dumps(entities_list, indent=2),
            "chunks_by_section": chunks_text
        }
    
    async def _call_llm_api(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Call LLM API for relationship extraction.
        
        Args:
            context: Global context dictionary
            
        Returns:
            List of relationship dictionaries
        """
        # Build user message with context data
        user_message = f"""
Please extract relationships from the following document data:

**Document Type**: {context['document_type']}

**Section Types**: {', '.join(context['section_types'])}

**Canonical Entities**:
{context['entities_json']}

**Document Chunks by Section**:
{context['chunks_by_section']}

Extract all relationships between these canonical entities based on the evidence in the chunks.
Return ONLY valid JSON following the schema defined in the system instructions.
"""
        
        try:
            # Use GeminiClient
            llm_response = await self.client.generate_content(
                contents=user_message,
                system_instruction=self.RELATIONSHIP_EXTRACTION_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse JSON response
            parsed = self._parse_response(llm_response)
            
            return parsed.get("relationships", [])
            
        except Exception as e:
            LOGGER.error(f"LLM call failed: {e}", exc_info=True)
            raise
    
    def _parse_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM response.
        
        Args:
            llm_response: Raw LLM response
            
        Returns:
            Parsed dictionary
        """
        # Remove markdown code fences if present
        llm_response = llm_response.strip()
        if llm_response.startswith("```"):
            lines = llm_response.split("\n")
            llm_response = "\n".join(lines[1:-1])
        
        try:
            return json.loads(llm_response)
        except json.JSONDecodeError as e:
            LOGGER.error(f"Failed to parse LLM response: {e}")
            return {"relationships": []}
    
    async def _create_relationship(
        self,
        document_id: UUID,
        relationship_data: Dict[str, Any],
        canonical_entities: List[CanonicalEntity]
    ) -> Optional[EntityRelationship]:
        """Create EntityRelationship record with flexible entity matching.
        
        Args:
            document_id: Document ID
            relationship_data: Relationship data from LLM
            canonical_entities: List of canonical entities
            
        Returns:
            Created relationship or None if invalid
        """
        # Validate relationship type
        rel_type = relationship_data.get("type")
        if rel_type not in VALID_RELATIONSHIP_TYPES:
            LOGGER.warning(f"Invalid relationship type: {rel_type}")
            return None
        
        # Get source and target identifiers from LLM
        source_id = relationship_data.get("source_entity_id") or relationship_data.get("source_canonical_id")
        target_id = relationship_data.get("target_entity_id") or relationship_data.get("target_canonical_id")
        
        if not source_id or not target_id:
            LOGGER.warning(
                f"Missing entity IDs in relationship",
                extra={"relationship_data": relationship_data}
            )
            return None
        
        # Try multiple matching strategies
        source_entity = self._find_entity(source_id, canonical_entities)
        target_entity = self._find_entity(target_id, canonical_entities)
        
        if not source_entity or not target_entity:
            LOGGER.warning(
                f"Could not find entities for relationship",
                extra={
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": rel_type,
                    "source_found": source_entity is not None,
                    "target_found": target_entity is not None
                }
            )
            return None
        
        # Create relationship
        relationship = EntityRelationship(
            source_entity_id=source_entity.id,
            target_entity_id=target_entity.id,
            relationship_type=rel_type,
            confidence=relationship_data.get("confidence", 0.8),
            attributes={"evidence": relationship_data.get("evidence", [])}
        )
        
        self.session.add(relationship)
        
        LOGGER.info(
            f"Created relationship: {source_entity.entity_type}({source_entity.canonical_key[:8]}) "
            f"--{rel_type}--> {target_entity.entity_type}({target_entity.canonical_key[:8]})"
        )
        
        return relationship
    
    def _find_entity(
        self,
        entity_identifier: str,
        canonical_entities: List[CanonicalEntity]
    ) -> Optional[CanonicalEntity]:
        """Find entity using flexible matching strategies.
        
        Tries in order:
        1. Exact canonical_key match
        2. Match by entity_type:normalized_value format
        3. Fuzzy match by normalized value (case-insensitive)
        
        Args:
            entity_identifier: Entity ID from LLM (could be canonical_key, value, or type:value)
            canonical_entities: List of canonical entities
            
        Returns:
            Matched entity or None
        """
        # Strategy 1: Exact canonical_key match
        for entity in canonical_entities:
            if entity.canonical_key == entity_identifier:
                return entity
        
        # Strategy 2: Match by "entity_type:normalized_value" format
        if ":" in entity_identifier:
            try:
                entity_type, value = entity_identifier.split(":", 1)
                for entity in canonical_entities:
                    entity_value = entity.attributes.get("normalized_value", "") if entity.attributes else ""
                    if (entity.entity_type.lower() == entity_type.lower() and 
                        entity_value.lower() == value.lower()):
                        return entity
            except ValueError:
                pass
        
        # Strategy 3: Fuzzy match by normalized value (case-insensitive)
        entity_identifier_lower = entity_identifier.lower().strip()
        for entity in canonical_entities:
            entity_value = entity.attributes.get("normalized_value", "") if entity.attributes else ""
            if entity_value and entity_value.lower().strip() == entity_identifier_lower:
                return entity
        
        # Strategy 4: Partial match (if identifier is contained in value or vice versa)
        for entity in canonical_entities:
            entity_value = entity.attributes.get("normalized_value", "") if entity.attributes else ""
            if entity_value:
                entity_value_lower = entity_value.lower().strip()
                if (len(entity_identifier_lower) > 3 and 
                    (entity_identifier_lower in entity_value_lower or 
                     entity_value_lower in entity_identifier_lower)):
                    return entity
        
        return None
