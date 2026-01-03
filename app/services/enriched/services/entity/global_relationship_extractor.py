"""Global relationship extractor service (Pass 2).

This service extracts relationships between entities using full document context
after canonical entity resolution. This is Pass 2 of the two-pass extraction strategy.
"""

from app.core.unified_llm import UnifiedLLMClient
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
    Document,
    DocumentChunk,
    SOVItem,
    LossRunClaim,
    DocumentTable,
    EntityMention,
    EntityEvidence,
)
from app.repositories.table_repository import TableRepository
from app.services.processed.services.chunking.hybrid_models import SectionType, SECTION_CONFIG
from app.prompts import RELATIONSHIP_EXTRACTION_PROMPT, VALID_RELATIONSHIP_TYPES
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Valid relationship types imported from centralized prompts


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
    
    # Relationship extraction prompt is imported from app.prompts
    # See app/prompts/system_prompts.py for the full prompt definition
    
    def __init__(
        self,
        session: AsyncSession,
        provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "openai/gpt-oss-20b:free",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        timeout: int = 90,
        max_retries: int = 3,
    ):
        """Initialize global relationship extractor.
        
        Args:
            session: Database session
            provider: LLM provider to use ("gemini" or "openrouter")
            gemini_api_key: Gemini API key
            gemini_model: Gemini model to use
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model to use
            openrouter_api_url: OpenRouter API URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.session = session
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
            "Initialized RelationshipExtractorGlobal",
            extra={"model": model}
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
        
        # Check if canonical entities are sparse (< 3 entities)
        is_sparse = len(canonical_entities) < 3
        
        if is_sparse:
            LOGGER.warning(
                f"Sparse canonical entities ({len(canonical_entities)}), will use chunk-level candidates",
                extra={
                    "document_id": str(document_id),
                    "canonical_count": len(canonical_entities)
                }
            )
        
        # Fetch document and chunks
        document = await self._fetch_document(document_id)
        chunks = await self._fetch_document_chunks(document_id)
        
        if not chunks:
            LOGGER.warning(
                f"No document chunks found for document",
                extra={"document_id": str(document_id)}
            )
            return []
        
        # Fetch all table data (SOV items, Loss Run claims, and DocumentTables)
        table_repo = TableRepository(self.session)
        sov_items = await table_repo.get_sov_items(document_id)
        loss_run_claims = await table_repo.get_loss_run_claims(document_id)
        document_tables = await table_repo.get_document_tables(document_id)
        
        LOGGER.info(
            f"Fetched table data for relationship extraction",
            extra={
                "document_id": str(document_id),
                "sov_items_count": len(sov_items),
                "loss_run_claims_count": len(loss_run_claims),
                "document_tables_count": len(document_tables)
            }
        )
        
        # Group chunks by section type (v2 architecture)
        section_chunks = self._group_chunks_by_section(chunks)
        
        # Build global context (includes chunk candidates if sparse, and all table data)
        context = await self._build_global_context(
            document=document,
            document_id=document_id,
            canonical_entities=canonical_entities,
            chunks=chunks,
            section_chunks=section_chunks,
            sov_items=sov_items,
            loss_run_claims=loss_run_claims,
            document_tables=document_tables,
            include_chunk_candidates=is_sparse
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
                    canonical_entities=canonical_entities,
                    chunks=chunks if is_sparse else None  # Pass chunks for temp entity reconciliation
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
        
        This method tries multiple strategies to find canonical entities:
        1. Via ChunkEntityLink (chunk-level links)
        2. Via DocumentEntityLink (document-level links)
        3. Fallback: Extract from NormalizedChunk.entities and resolve on-the-fly
        
        Args:
            document_id: Document ID
            
        Returns:
            List of canonical entities
        """
        from app.database.models import ChunkEntityLink, DocumentEntityLink
        
        # Strategy 1: Get canonical entities via EntityEvidence (preferred - doc-aligned)
        stmt = select(CanonicalEntity).join(
            EntityEvidence,
            EntityEvidence.canonical_entity_id == CanonicalEntity.id
        ).where(
            EntityEvidence.document_id == document_id
        ).distinct()
        
        result = await self.session.execute(stmt)
        canonical_entities = list(result.scalars().all())
        
        LOGGER.debug(
            f"Found {len(canonical_entities)} canonical entities via EntityEvidence",
            extra={"document_id": str(document_id)}
        )
        
        # Strategy 2: If no entities found, try DocumentEntityLink
        if not canonical_entities:
            stmt = select(CanonicalEntity).join(
                DocumentEntityLink,
                DocumentEntityLink.canonical_entity_id == CanonicalEntity.id
            ).where(
                DocumentEntityLink.document_id == document_id
            ).distinct()
            
            result = await self.session.execute(stmt)
            canonical_entities = list(result.scalars().all())
            
            LOGGER.debug(
                f"Found {len(canonical_entities)} canonical entities via DocumentEntityLink",
                extra={"document_id": str(document_id)}
            )
        
        # Strategy 3: Fallback - Extract entities from EntityMention and resolve
        if not canonical_entities:
            LOGGER.warning(
                f"No canonical entities found via links. Attempting fallback: extracting from entity_mentions",
                extra={"document_id": str(document_id)}
            )
            
            # Fetch entity mentions for this document
            stmt = select(EntityMention).where(
                EntityMention.document_id == document_id
            )
            result = await self.session.execute(stmt)
            mentions = list(result.scalars().all())
            
            # Extract all entities from mentions and normalize format
            all_entity_dicts = []
            for mention in mentions:
                extracted_fields = mention.extracted_fields or {}
                normalized_entity = {
                    "entity_type": mention.entity_type,
                    "normalized_value": extracted_fields.get("normalized_value", mention.mention_text),
                    "raw_value": mention.mention_text,
                    "confidence": float(mention.confidence) if mention.confidence else 0.8,
                    **extracted_fields
                }
                
                # Only add if we have required fields
                if normalized_entity["entity_type"] and normalized_entity["normalized_value"]:
                    all_entity_dicts.append(normalized_entity)
            
            if all_entity_dicts:
                LOGGER.info(
                    f"Found {len(all_entity_dicts)} raw entities in chunks. Resolving to canonical entities...",
                    extra={"document_id": str(document_id)}
                )
                
                # Resolve entities to canonical form
                from app.services.enriched.services.entity.resolver import EntityResolver
                resolver = EntityResolver(self.session)
                
                canonical_ids = await resolver.resolve_entities_batch(
                    entities=all_entity_dicts,
                    chunk_id=None,  # Document-level resolution
                    document_id=document_id
                )
                
                # Fetch the resolved canonical entities
                if canonical_ids:
                    # Flush to ensure entities are persisted
                    await self.session.flush()
                    
                    stmt = select(CanonicalEntity).where(
                        CanonicalEntity.id.in_(canonical_ids)
                    )
                    result = await self.session.execute(stmt)
                    canonical_entities = list(result.scalars().all())
                    
                    LOGGER.info(
                        f"Resolved {len(canonical_entities)} canonical entities from chunk entities",
                        extra={"document_id": str(document_id), "resolved_count": len(canonical_entities)}
                    )
        
        LOGGER.info(
            f"Total canonical entities fetched: {len(canonical_entities)}",
            extra={"document_id": str(document_id)}
        )
        
        return canonical_entities
    
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
    
    async def _fetch_document_chunks(
        self,
        document_id: UUID
    ) -> List[DocumentChunk]:
        """Fetch document chunks for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of document chunks
        """
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
        )
        
        result = await self.session.execute(stmt)
        chunks = result.scalars().all()
        
        LOGGER.debug(
            f"Fetched {len(chunks)} document chunks",
            extra={"document_id": str(document_id)}
        )
        
        return list(chunks)
    
    async def _fetch_normalized_chunks(
        self,
        document_id: UUID
    ) -> List[NormalizedChunk]:
        """Fetch normalized chunks for a document (legacy fallback).
        
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
    
    def _group_chunks_by_section(
        self,
        chunks: List[DocumentChunk]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group chunks by section type for v2 section-aware processing.
        
        This method organizes chunks into semantic sections matching the v2
        architecture's SectionType enum, enabling better relationship extraction
        by providing section context.
        
        Args:
            chunks: List of document chunks
            
        Returns:
            Dictionary mapping section type to list of chunk data
        """
        section_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        # Map v2 SectionType values for reference
        v2_section_types = {st.value for st in SectionType}
        
        for chunk in chunks:
            # Get section type from DocumentChunk
            section_type = chunk.section_type
            
            # Normalize to v2 SectionType or use "unknown"
            if section_type and section_type.lower() in v2_section_types:
                section_key = section_type.lower()
            elif section_type:
                section_key = section_type.lower()
            else:
                section_key = SectionType.UNKNOWN.value
            
            if section_key not in section_groups:
                section_groups[section_key] = []
            
            # Build chunk data with v2 metadata
            chunk_data = {
                "chunk_id": str(chunk.id),
                "stable_chunk_id": chunk.stable_chunk_id,
                "page_number": chunk.page_number,
                "section_type": section_key,
                "subsection_type": chunk.subsection_type,
                "text": chunk.raw_text,
                "token_count": chunk.token_count,
            }
            section_groups[section_key].append(chunk_data)
        
        LOGGER.debug(
            "Grouped chunks by section type",
            extra={
                "section_count": len(section_groups),
                "sections": {k: len(v) for k, v in section_groups.items()}
            }
        )
        
        return section_groups
    
    async def _build_global_context(
        self,
        document: Optional[Document],
        document_id: UUID,
        canonical_entities: List[CanonicalEntity],
        chunks: List[DocumentChunk],
        section_chunks: Dict[str, List[Dict[str, Any]]],
        sov_items: List[SOVItem],
        loss_run_claims: List[LossRunClaim],
        document_tables: List[DocumentTable],
        include_chunk_candidates: bool = False
    ) -> Dict[str, Any]:
        """Build global context for LLM using v2 section-aware architecture.
        
        This method builds a comprehensive context including:
        - Canonical entities with their attributes
        - Section-grouped chunks (v2 super-chunk style)
        - All table data (SOV items, Loss Run claims, DocumentTables)
        - Section processing priorities from v2 config
        
        Args:
            document: Document record
            canonical_entities: List of canonical entities
            chunks: List of normalized chunks (for fallback)
            section_chunks: Chunks grouped by section type (v2 style)
            sov_items: SOV items extracted from tables
            loss_run_claims: Loss Run claims extracted from tables
            document_tables: All DocumentTable records
            include_chunk_candidates: Whether to include chunk-level entity candidates
            
        Returns:
            Context dictionary for LLM
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
                "confidence": confidence,
                "source": "canonical"
            })
        
        # Add chunk-level candidates if canonical entities are sparse
        chunk_candidates = []
        if include_chunk_candidates:
            chunk_candidates = await self._build_chunk_entity_candidates(document_id)
            entities_list.extend(chunk_candidates)
            
            LOGGER.info(
                f"Added {len(chunk_candidates)} chunk-level entity candidates",
                extra={
                    "canonical_count": len(canonical_entities),
                    "candidate_count": len(chunk_candidates)
                }
            )
        
        # Build section-aware chunks text (v2 super-chunk style)
        # Prioritize sections based on v2 SECTION_CONFIG
        section_priority = {}
        for section_type in SectionType:
            config = SECTION_CONFIG.get(section_type, SECTION_CONFIG[SectionType.UNKNOWN])
            section_priority[section_type.value] = config["priority"]
        
        # Sort sections by priority (lower = higher priority)
        sorted_sections = sorted(
            section_chunks.keys(),
            key=lambda s: section_priority.get(s, 10)
        )
        
        # Format chunks by section with v2 metadata
        chunks_by_section_list = []
        for section_key in sorted_sections:
            section_data = section_chunks[section_key]
            config = SECTION_CONFIG.get(
                SectionType(section_key) if section_key in [st.value for st in SectionType] else SectionType.UNKNOWN,
                SECTION_CONFIG[SectionType.UNKNOWN]
            )
            
            section_info = {
                "section_type": section_key,
                "section_name": section_key.replace("_", " ").title(),
                "processing_priority": config["priority"],
                "requires_llm": config["requires_llm"],
                "table_only": config["table_only"],
                "chunk_count": len(section_data),
                "total_tokens": sum(c.get("token_count", 0) for c in section_data),
                "page_range": sorted(set(c.get("page_number", 0) for c in section_data)),
                "chunks": section_data
            }
            chunks_by_section_list.append(section_info)
        
        # Format chunks text for prompt (simplified view)
        chunks_text = ""
        for section_info in chunks_by_section_list:
            section_key = section_info["section_type"]
            priority_label = f"(priority: {section_info['processing_priority']})"
            table_only_label = " [TABLE-ONLY]" if section_info["table_only"] else ""
            
            chunks_text += f"\n### Section: {section_info['section_name']} {priority_label}{table_only_label}\n"
            chunks_text += f"Pages: {section_info['page_range']}, Chunks: {section_info['chunk_count']}\n"
            
            for chunk_data in section_info["chunks"]:
                chunks_text += f"\n[Chunk {chunk_data['chunk_id'][:8]}...]\n"
                chunks_text += chunk_data["text"][:2000]  # Limit text length per chunk
                if len(chunk_data["text"]) > 2000:
                    chunks_text += "\n... (truncated)"
            chunks_text += "\n"
        
        # Format SOV items for prompt
        sov_items_list = []
        for sov in sov_items:
            sov_items_list.append({
                "sov_id": f"sov-{str(sov.id)[:8]}",
                "location_number": sov.location_number,
                "building_number": sov.building_number,
                "description": sov.description,
                "address": sov.address,
                "construction_type": sov.construction_type,
                "occupancy": sov.occupancy,
                "year_built": sov.year_built,
                "square_footage": sov.square_footage,
                "building_limit": float(sov.building_limit) if sov.building_limit else None,
                "contents_limit": float(sov.contents_limit) if sov.contents_limit else None,
                "bi_limit": float(sov.bi_limit) if sov.bi_limit else None,
                "total_insured_value": float(sov.total_insured_value) if sov.total_insured_value else None,
            })
        
        # Format Loss Run claims for prompt
        loss_run_list = []
        for claim in loss_run_claims:
            loss_run_list.append({
                "claim_id": f"claim-{str(claim.id)[:8]}",
                "claim_number": claim.claim_number,
                "policy_number": claim.policy_number,
                "insured_name": claim.insured_name,
                "loss_date": claim.loss_date.isoformat() if claim.loss_date else None,
                "report_date": claim.report_date.isoformat() if claim.report_date else None,
                "cause_of_loss": claim.cause_of_loss,
                "description": claim.description,
                "incurred_amount": float(claim.incurred_amount) if claim.incurred_amount else None,
                "paid_amount": float(claim.paid_amount) if claim.paid_amount else None,
                "reserve_amount": float(claim.reserve_amount) if claim.reserve_amount else None,
                "status": claim.status,
            })
        
        # Format all DocumentTables for prompt (covers all table types)
        document_tables_list = []
        for doc_table in document_tables:
            table_data = {
                "table_id": f"tbl-{str(doc_table.id)[:8]}",
                "stable_table_id": doc_table.stable_table_id,
                "page_number": doc_table.page_number,
                "table_type": doc_table.table_type,  # property_sov, loss_run, premium_schedule, coverage_schedule, etc.
                "num_rows": doc_table.num_rows,
                "num_cols": doc_table.num_cols,
                "canonical_headers": doc_table.canonical_headers,
                "classification_confidence": float(doc_table.classification_confidence) if doc_table.classification_confidence else None,
            }
            
            # Include raw markdown for context if available
            if doc_table.raw_markdown:
                table_data["raw_markdown"] = doc_table.raw_markdown[:1000]  # Limit size
                if len(doc_table.raw_markdown) > 1000:
                    table_data["raw_markdown"] += "\n... (truncated)"
            
            document_tables_list.append(table_data)
        
        return {
            "document_type": document.classifications[0].classified_type if document and document.classifications else "unknown",
            "section_types": sorted_sections,
            "section_summary": {
                section_key: {
                    "chunk_count": len(section_chunks.get(section_key, [])),
                    "priority": section_priority.get(section_key, 10)
                }
                for section_key in sorted_sections
            },
            "entities_json": json.dumps(entities_list, indent=2),
            "chunks_by_section": chunks_text,
            "chunks_by_section_structured": json.dumps(chunks_by_section_list, indent=2),
            "sov_items_json": json.dumps(sov_items_list, indent=2),
            "loss_run_claims_json": json.dumps(loss_run_list, indent=2),
            "document_tables_json": json.dumps(document_tables_list, indent=2),
            "has_chunk_candidates": include_chunk_candidates,
            "candidate_count": len(chunk_candidates) if include_chunk_candidates else 0,
            "sov_items_count": len(sov_items_list),
            "loss_run_claims_count": len(loss_run_list),
            "document_tables_count": len(document_tables_list),
            # v2 architecture metadata
            "architecture_version": "v2",
            "section_aware_chunking": True,
        }
    
    async def _build_chunk_entity_candidates(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Build candidate entities from entity_mentions when canonical sparse.
        
        Args:
            document_id: Document ID
            
        Returns:
            List of chunk-level entity candidates with temporary IDs
        """
        # Fetch entity mentions for this document
        stmt = select(EntityMention).where(
            EntityMention.document_id == document_id
        )
        result = await self.session.execute(stmt)
        mentions = list(result.scalars().all())
        
        candidates = []
        
        for mention in mentions:
            extracted_fields = mention.extracted_fields or {}
            normalized_value = extracted_fields.get("normalized_value", mention.mention_text)
            
            # Assign temporary ID
            temp_id = f"temp_{mention.id}_{mention.entity_type}_{hash(normalized_value)}"[:64]
            
            candidates.append({
                "entity_id": temp_id,
                "entity_type": mention.entity_type,
                "value": normalized_value,
                "confidence": float(mention.confidence) if mention.confidence else 0.5,
                "source": "chunk_level",
                "chunk_id": str(mention.source_document_chunk_id) if mention.source_document_chunk_id else None,
                "mention_id": str(mention.id)
            })
        
        LOGGER.debug(
            f"Built {len(candidates)} chunk-level entity candidates from entity_mentions",
            extra={"candidate_count": len(candidates)}
        )
        
        return candidates
    
    async def _call_llm_api(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Call LLM API for relationship extraction using v2 section-aware context.
        
        Args:
            context: Global context dictionary with v2 section-aware data
            
        Returns:
            List of relationship dictionaries
        """
        # Build user message with v2 section-aware context data
        user_message = f"""
Please extract relationships from the following insurance document data.

**Architecture**: v2 Section-Aware Processing
**Document Type**: {context['document_type']}

**Section Summary** (ordered by processing priority):
{json.dumps(context.get('section_summary', {}), indent=2)}

**Canonical Entities** ({len(json.loads(context['entities_json']))} entities):
{context['entities_json']}

{"**Note**: Some entities are chunk-level candidates (source='chunk_level') because canonical entities are sparse. Prefer canonical entities but use candidates when needed." if context.get('has_chunk_candidates') else ""}

**Document Chunks by Section** (v2 super-chunk style):
{context['chunks_by_section']}

**Table Data Summary**:
- SOV Items: {context.get('sov_items_count', 0)} items
- Loss Run Claims: {context.get('loss_run_claims_count', 0)} claims
- Document Tables: {context.get('document_tables_count', 0)} tables (all types)

**SOV Items** (Statement of Values - property locations):
{context.get('sov_items_json', '[]')}

**Loss Run Claims** (claims history):
{context.get('loss_run_claims_json', '[]')}

**Document Tables** (all table types: property_sov, loss_run, premium_schedule, coverage_schedule, etc.):
{context.get('document_tables_json', '[]')}

**Relationship Extraction Instructions**:
1. Extract relationships between canonical entities based on evidence in section chunks
2. Use section context to boost confidence (e.g., declarations section for policy relationships)
3. For table data:
   - SOV items → Create LOCATED_AT relationships (Policy/Entity → Address)
   - Loss Run claims → Create HAS_CLAIM relationships (Policy → Claim)
   - Premium/Coverage tables → Create HAS_COVERAGE, HAS_LIMIT, HAS_DEDUCTIBLE relationships
4. Match policy_number, claim_number, and addresses between tables and canonical entities
5. Sections marked [TABLE-ONLY] should primarily use table data, not LLM extraction

Return ONLY valid JSON following the schema defined in the system instructions.
"""
        
        try:
            # Use GeminiClient
            response = await self.client.generate_content(
                contents=user_message,
                system_instruction=RELATIONSHIP_EXTRACTION_PROMPT,
                generation_config={"response_mime_type": "application/json"}
            )
            
            # Parse JSON response
            parsed = self._parse_response(response)
            
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
        canonical_entities: List[CanonicalEntity],
        chunks: Optional[List[NormalizedChunk]] = None
    ) -> Optional[EntityRelationship]:
        """Create EntityRelationship record with flexible entity matching.
        
        Args:
            document_id: Document ID
            relationship_data: Relationship data from LLM
            canonical_entities: List of canonical entities
            chunks: Optional chunks for temp entity reconciliation
            
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
        source_entity = self._find_entity(source_id, canonical_entities, chunks)
        target_entity = self._find_entity(target_id, canonical_entities, chunks)
        
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
        
        # Build attributes with evidence and provenance
        attributes = {
            "evidence": relationship_data.get("evidence", []),
            "source": "llm_extraction",
            "prompt_version": "v4.0"
        }
        
        # Add table data references if present in evidence
        evidence_list = relationship_data.get("evidence", [])
        for ev in evidence_list:
            if isinstance(ev, dict):
                if "sov_id" in ev:
                    attributes["sov_reference"] = ev.get("sov_id")
                if "claim_id" in ev:
                    attributes["claim_reference"] = ev.get("claim_id")
        
        # Create relationship
        relationship = EntityRelationship(
            source_entity_id=source_entity.id,
            target_entity_id=target_entity.id,
            relationship_type=rel_type,
            confidence=relationship_data.get("confidence", 0.8),
            attributes=attributes
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
        canonical_entities: List[CanonicalEntity],
        chunks: Optional[List[NormalizedChunk]] = None
    ) -> Optional[CanonicalEntity]:
        """Find entity using flexible matching strategies.
        
        Tries in order:
        1. Exact canonical_key match
        2. Match by entity_type:normalized_value format
        3. Fuzzy match by normalized value (case-insensitive)
        4. If chunks provided and identifier starts with 'temp_', reconcile to canonical
        
        Args:
            entity_identifier: Entity ID from LLM (could be canonical_key, value, or type:value)
            canonical_entities: List of canonical entities
            chunks: Optional chunks for temp entity reconciliation
            
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
        
        # Strategy 5: Reconcile temporary chunk-level entity to canonical
        if chunks and entity_identifier.startswith('temp_'):
            reconciled = self._reconcile_temp_entity(entity_identifier, canonical_entities, chunks)
            if reconciled:
                LOGGER.debug(
                    f"Reconciled temp entity {entity_identifier[:32]}... to canonical",
                    extra={"canonical_id": reconciled.canonical_key[:16]}
                )
                return reconciled
        
        return None
    
    def _reconcile_temp_entity(
        self,
        temp_id: str,
        canonical_entities: List[CanonicalEntity],
        chunks: List[NormalizedChunk]
    ) -> Optional[CanonicalEntity]:
        """Reconcile temporary chunk-level entity to canonical entity.
        
        Args:
            temp_id: Temporary entity ID (format: temp_{chunk_id}_{type}_{hash})
            canonical_entities: List of canonical entities
            chunks: List of chunks
            
        Returns:
            Matched canonical entity or None
        """
        # Extract chunk_id from temp_id
        try:
            parts = temp_id.split('_')
            if len(parts) < 3:
                return None
            
            chunk_id_str = parts[1]
            entity_type = parts[2] if len(parts) > 2 else None
            
            # Find the chunk
            chunk = next((c for c in chunks if str(c.id) == chunk_id_str), None)
            if not chunk or not chunk.entities:
                return None
            
            # Find the entity in chunk by type and hash match
            for chunk_entity in chunk.entities:
                if chunk_entity.get('entity_type') == entity_type:
                    # Try to match to canonical by normalized value
                    normalized_value = chunk_entity.get('normalized_value', '')
                    
                    for canonical in canonical_entities:
                        canonical_value = canonical.attributes.get('normalized_value', '') if canonical.attributes else ''
                        
                        if (canonical.entity_type == entity_type and
                            canonical_value.lower().strip() == normalized_value.lower().strip()):
                            return canonical
            
        except Exception as e:
            LOGGER.warning(f"Failed to reconcile temp entity: {e}")
        
        return None
