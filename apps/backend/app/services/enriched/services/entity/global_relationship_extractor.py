"""Global relationship extractor service.

This service extracts relationships between entities using 
full document context after canonical entity resolution.
"""

from app.core.unified_llm import UnifiedLLMClient
import json
import asyncio
from typing import List, Dict, Any, Optional
from uuid import UUID

from app.utils.json_parser import parse_json_safely

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    CanonicalEntity,
    EntityRelationship,
    Document,
    DocumentChunk,
    SOVItem,
    LossRunClaim,
    DocumentTable,
    EntityMention,
    EntityEvidence,
)
from app.repositories.entity_mention_repository import EntityMentionRepository
from app.repositories.table_repository import TableRepository
from app.services.processed.services.chunking.hybrid_models import SectionType, SECTION_CONFIG
from app.prompts.system_prompts import (
    RELATIONSHIP_EXTRACTION_PROMPT,
    VALID_RELATIONSHIP_TYPES,
    CROSS_BATCH_SYNTHESIS_PROMPT_TEMPLATE
)
from app.utils.relationship_config import SECTION_PAIRINGS
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


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
        provider: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
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
        document_id: UUID,
        workflow_id: Optional[UUID] = None
    ) -> List[EntityRelationship]:
        """Extract relationships for a document using global context.
        
        Args:
            document_id: Document ID
            workflow_id: ID of the workflow
            
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
        
        # Group chunks by section type
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
                    chunks=chunks if is_sparse else None,
                    workflow_id=workflow_id
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
        
        This method tries multiple strategies to find canonical entities
        
        Args:
            document_id: Document ID
            
        Returns:
            List of canonical entities
        """
        
        # Get canonical entities via EntityEvidence
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
        #Extract entities from EntityMention and resolve to canonical entities
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
    
    def _group_chunks_by_section(
        self,
        chunks: List[DocumentChunk]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group chunks by section type for section-aware processing.
        
        This method organizes chunks into semantic sections matching the SectionType enum,
        enabling better relationship extraction by providing section context.
        
        Args:
            chunks: List of document chunks
            
        Returns:
            Dictionary mapping section type to list of chunk data
        """
        section_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        # Map SectionType values for reference
        section_types = {st.value for st in SectionType}
        
        for chunk in chunks:
            # Get section type from DocumentChunk
            section_type = chunk.section_type
            
            # Normalize to SectionType or use "unknown"
            if section_type and section_type.lower() in section_types:
                section_key = section_type.lower()
            elif section_type:
                section_key = section_type.lower()
            else:
                section_key = SectionType.UNKNOWN.value
            
            if section_key not in section_groups:
                section_groups[section_key] = []
            
            # Build chunk data with metadata
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

    def _partition_sections_into_batches(
        self,
        section_chunks: Dict[str, List[Dict[str, Any]]],
        sov_items: List[SOVItem],
        loss_run_claims: List[LossRunClaim],
        document_tables: List[DocumentTable]
    ) -> List[Dict[str, Any]]:
        """Partition sections into semantic batches based on relationship bridges.

        Instead of processing one section per batch, this groups related sections
        that commonly have cross-section relationships. This allows the LLM to see
        both sides of a relationship (e.g., Policy in declarations + Coverage in coverages).

        Args:
            section_chunks: Chunks grouped by section type
            sov_items: SOV items for location relationships
            loss_run_claims: Loss run claims for claim relationships
            document_tables: All document tables for routing

        Returns:
            List of batch configurations with sections and routed table data
        """
        available_sections = set(section_chunks.keys())
        batches = []
        processed_sections = set()

        # Sort pairings by priority
        sorted_pairings = sorted(SECTION_PAIRINGS, key=lambda p: p["priority"])

        for pairing in sorted_pairings:
            # Find which sections from this pairing are available
            pairing_sections = [s for s in pairing["sections"] if s in available_sections]

            if not pairing_sections:
                continue  # Skip if no sections from this pairing exist

            # Build batch configuration
            batch = {
                "name": pairing["name"],
                "description": pairing["description"],
                "sections": pairing_sections,
                "expected_rels": pairing["expected_rels"],
                "priority": pairing["priority"],
            }

            # Route table data to this batch only if relevant
            batch["sov_items"] = sov_items if pairing["include_sov"] else []
            batch["loss_run_claims"] = loss_run_claims if pairing["include_loss_runs"] else []

            # Route document tables by table_type
            if pairing["table_types"]:
                batch["document_tables"] = [
                    tbl for tbl in document_tables
                    if tbl.table_type in pairing["table_types"]
                ]
            else:
                batch["document_tables"] = []

            # Merge section chunks for this batch
            batch_chunks = []
            for section_key in pairing_sections:
                batch_chunks.extend(section_chunks[section_key])
                processed_sections.add(section_key)

            batch["chunks"] = batch_chunks
            batch["section_count"] = len(pairing_sections)
            batch["chunk_count"] = len(batch_chunks)
            batch["total_tokens"] = sum(c.get("token_count", 0) for c in batch_chunks)

            batches.append(batch)

        # Catch any sections not covered by pairings (fallback to individual batches)
        uncovered_sections = available_sections - processed_sections
        for section_key in sorted(uncovered_sections):
            batch = {
                "name": f"uncovered_{section_key}",
                "description": f"Uncovered section: {section_key}",
                "sections": [section_key],
                "expected_rels": [],
                "priority": 99,
                "sov_items": [],
                "loss_run_claims": [],
                "document_tables": [],
                "chunks": section_chunks[section_key],
                "section_count": 1,
                "chunk_count": len(section_chunks[section_key]),
                "total_tokens": sum(c.get("token_count", 0) for c in section_chunks[section_key]),
            }
            batches.append(batch)

        LOGGER.info(
            f"Partitioned {len(available_sections)} sections into {len(batches)} semantic batches",
            extra={
                "total_sections": len(available_sections),
                "batches": len(batches),
                "batch_names": [b["name"] for b in batches],
                "uncovered_sections": list(uncovered_sections)
            }
        )

        return batches

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
        """Build global context for LLM using section-aware.
        
        This method builds a comprehensive context including:
        - Canonical entities with their attributes
        - Section-grouped chunks (super-chunk style)
        - All table data (SOV items, Loss Run claims, DocumentTables)
        - Section processing priorities from config
        
        Args:
            document: Document record
            canonical_entities: List of canonical entities
            chunks: List of normalized chunks (for fallback)
            section_chunks: Chunks grouped by section type
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
            # Extract data from attributes JSONB field
            attr = entity.attributes or {}
            value = attr.get("normalized_value", "")
            confidence = attr.get("confidence", 0.9)
            
            # Prepare full entity info with all attributes for LLM
            entity_info = {
                "entity_id": entity.canonical_key,  # This is the stable ID used in prompts
                "entity_type": entity.entity_type,
                "value": value,
                "confidence": confidence,
                "source": "canonical"
            }
            # Add all other attributes except internal bookkeeping
            for k, v in attr.items():
                if k not in ["normalized_value", "raw_value", "confidence"]:
                    entity_info[f"attr_{k}"] = v
            
            entities_list.append(entity_info)
        
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
        
        # Build section-aware chunks text (super-chunk style)
        # Prioritize sections based on SECTION_CONFIG
        section_priority = {}
        for section_type in SectionType:
            config = SECTION_CONFIG.get(section_type, SECTION_CONFIG[SectionType.UNKNOWN])
            section_priority[section_type.value] = config["priority"]
        
        # Sort sections by priority (lower = higher priority)
        sorted_sections = sorted(
            section_chunks.keys(),
            key=lambda s: section_priority.get(s, 10)
        )
        
        # Format chunks by section with metadata
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
            "document_type": document.classifications[0].page_type if document and document.classifications else "unknown",
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
        mention_repo = EntityMentionRepository(self.session)
        mentions = await mention_repo.get_by_document_id(document_id)
        
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
        """Call LLM API for relationship extraction using semantic section batches.

        This implements semantic batch-oriented processing where related sections
        are grouped together (e.g., declarations + coverages) to enable extraction
        of cross-section relationships while avoiding output truncation.

        Args:
            context: Global context dictionary with section-aware data

        Returns:
            List of aggregated relationship dictionaries
        """
        # Get section chunks, SOV items, loss runs, and tables from context
        section_chunks_str = context.get("chunks_by_section_structured")
        if not section_chunks_str:
            LOGGER.warning("No structured sections found for batching, falling back to full context")
            user_message = self._build_user_message(context)
            return await self._execute_llm_call(user_message)

        try:
            section_data = json.loads(section_chunks_str)
        except Exception as e:
            LOGGER.error(f"Failed to parse structured sections: {e}")
            user_message = self._build_user_message(context)
            return await self._execute_llm_call(user_message)

        if not section_data:
            LOGGER.warning("Empty section data, falling back to full context")
            user_message = self._build_user_message(context)
            return await self._execute_llm_call(user_message)

        # Convert section_data list into a dict keyed by section_type for easier lookup
        section_chunks = {}
        for section_info in section_data:
            section_type = section_info.get("section_type")
            if section_type:
                section_chunks[section_type] = section_info.get("chunks", [])

        # Get table data from context (already as JSON strings)
        sov_items_str = context.get("sov_items_json", "[]")
        loss_run_claims_str = context.get("loss_run_claims_json", "[]")
        document_tables_str = context.get("document_tables_json", "[]")

        try:
            document_tables_data = json.loads(document_tables_str)
        except Exception as e:
            LOGGER.error(f"Failed to parse document tables data: {e}")
            document_tables_data = []

        # Create empty lists for partitioning
        # We'll route the actual JSON strings to batches based on configuration
        # The partitioning logic only needs empty lists since it checks include_sov/include_loss_runs flags
        empty_sov_items = []
        empty_loss_runs = []
        empty_tables = []

        # Partition sections into semantic batches
        semantic_batches = self._partition_sections_into_batches(
            section_chunks=section_chunks,
            sov_items=empty_sov_items,  # Routing handled via JSON strings
            loss_run_claims=empty_loss_runs,  # Routing handled via JSON strings
            document_tables=empty_tables  # Routing handled via JSON strings
        )

        if not semantic_batches:
            LOGGER.warning("No semantic batches created, falling back to full context")
            user_message = self._build_user_message(context)
            return await self._execute_llm_call(user_message)

        all_relationships = []

        # Process each semantic batch
        for i, batch in enumerate(semantic_batches):
            batch_name = batch.get("name", "unknown")
            LOGGER.info(
                f"Processing relationship extraction batch {i+1}/{len(semantic_batches)}: {batch_name}",
                extra={
                    "batch_name": batch_name,
                    "sections": batch.get("sections", []),
                    "section_count": batch.get("section_count", 0),
                    "chunk_count": batch.get("chunk_count", 0),
                }
            )

            # Route table data to batch based on configuration
            # Since we don't have the actual objects, we'll filter the JSON arrays
            if batch.get("include_sov"):
                batch["sov_items_json"] = sov_items_str
            else:
                batch["sov_items_json"] = "[]"

            if batch.get("include_loss_runs"):
                batch["loss_run_claims_json"] = loss_run_claims_str
            else:
                batch["loss_run_claims_json"] = "[]"

            # Filter document tables by table_type if specified
            if batch.get("table_types"):
                filtered_tables = [
                    tbl for tbl in document_tables_data
                    if tbl.get("table_type") in batch["table_types"]
                ]
                batch["document_tables_json"] = json.dumps(filtered_tables, indent=2)
            else:
                batch["document_tables_json"] = "[]"

            # Build batch-specific user message
            user_message = self._build_batch_user_message(context, batch)

            try:
                # Execute LLM call for this batch
                batch_data = await self._execute_llm_call(user_message)

                # Tag relationships with batch name for provenance tracking
                for rel in batch_data:
                    if "attributes" not in rel:
                        rel["attributes"] = {}
                    rel["attributes"]["extraction_batch"] = batch_name
                    rel["attributes"]["extraction_sections"] = batch.get("sections", [])

                all_relationships.extend(batch_data)

                LOGGER.info(
                    f"Batch {batch_name} extracted {len(batch_data)} relationships",
                    extra={
                        "batch_name": batch_name,
                        "relationships_count": len(batch_data)
                    }
                )

            except Exception as e:
                LOGGER.error(
                    f"Batch extraction failed for {batch_name}: {e}",
                    extra={"batch_name": batch_name},
                    exc_info=True
                )
                # Continue with next batch to be resilient
                continue

        # Deduplicate relationships
        unique_relationships = self._deduplicate_relationships(all_relationships)

        LOGGER.info(
            f"Completed semantic batch relationship extraction",
            extra={
                "total_batches": len(semantic_batches),
                "raw_relationships": len(all_relationships),
                "unique_relationships": len(unique_relationships)
            }
        )

        # Run cross-batch synthesis pass to capture missing cross-pairing relationships
        try:
            cross_batch_relationships = await self._cross_batch_synthesis_pass(
                context=context,
                existing_relationships=unique_relationships,
                semantic_batches=semantic_batches
            )

            if cross_batch_relationships:
                LOGGER.info(
                    f"Cross-batch synthesis discovered {len(cross_batch_relationships)} additional relationships",
                    extra={"cross_batch_count": len(cross_batch_relationships)}
                )

                # Merge and deduplicate again
                all_relationships.extend(cross_batch_relationships)
                unique_relationships = self._deduplicate_relationships(all_relationships)
        except Exception as e:
            LOGGER.error(
                f"Cross-batch synthesis pass failed: {e}",
                exc_info=True
            )
            # Continue with existing relationships if synthesis fails

        LOGGER.info(
            f"Final relationship extraction completed",
            extra={
                "total_batches": len(semantic_batches),
                "final_unique_relationships": len(unique_relationships)
            }
        )

        return unique_relationships

    async def _execute_llm_call(self, user_message: str) -> List[Dict[str, Any]]:
        """Internal helper to execute a single LLM call and parse relationships.
        
        Args:
            user_message: The formatted user prompt
            
        Returns:
            List of extracted relationships
        """
        try:
            # Use GeminiClient / UnifiedLLMClient
            response = await self.client.generate_content(
                contents=user_message,
                system_instruction=RELATIONSHIP_EXTRACTION_PROMPT,
                generation_config={
                    "response_mime_type": "application/json",
                    "max_output_tokens": 64000 
                }
            )
            
            # Parse JSON response
            parsed = self._parse_response(response)
            
            return parsed.get("relationships", [])
            
        except Exception as e:
            LOGGER.error(f"LLM call execution failed: {e}", exc_info=True)
            raise

    def _deduplicate_relationships(self, relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate relationships based on source, target, and type.
        
        When duplicates are found, evidence is merged.
        """
        seen = {}  # (source, target, type) -> relationship_dict
        
        for rel in relationships:
            source = rel.get("source_entity_id") or rel.get("source_canonical_id")
            target = rel.get("target_entity_id") or rel.get("target_canonical_id")
            rel_type = (rel.get("type") or rel.get("relationship_type") or "").upper()
            
            if not source or not target or not rel_type:
                continue
                
            # Create a stable key
            key = (str(source), str(target), rel_type)
            
            if key not in seen:
                seen[key] = rel
            else:
                # Merge evidence if present
                existing = seen[key]
                existing_attr = existing.get("attributes", {})
                new_attr = rel.get("attributes", {})
                
                existing_evidence = existing_attr.get("evidence", [])
                new_evidence = new_attr.get("evidence", [])
                
                # Combine unique evidence
                # Simple deduplication by quote/table_id
                combined_evidence = list(existing_evidence)
                for new_ev in new_evidence:
                    if new_ev not in combined_evidence:
                        combined_evidence.append(new_ev)
                
                if "attributes" not in existing:
                    existing["attributes"] = {}
                existing["attributes"]["evidence"] = combined_evidence
                
                # Update confidence to max of seen
                existing["confidence"] = max(existing.get("confidence", 0), rel.get("confidence", 0))
                
        return list(seen.values())

    async def _cross_batch_synthesis_pass(
        self,
        context: Dict[str, Any],
        existing_relationships: List[Dict[str, Any]],
        semantic_batches: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Run a focused synthesis pass to discover missing cross-batch relationships.

        This addresses the limitation where relationships between entities from different
        semantic groups (e.g., Policy->Exclusion, Endorsement->Coverage) may be missed
        because they weren't in the same batch.

        Strategy:
        - Present all canonical entities organized by type
        - Show existing relationships organized by batch
        - Ask LLM to identify missing cross-batch relationships
        - Focus on common cross-pairing patterns

        Args:
            context: Global context with all entities
            existing_relationships: Relationships extracted from semantic batches
            semantic_batches: List of semantic batch configurations

        Returns:
            List of additional relationships discovered
        """
        LOGGER.info("Starting cross-batch synthesis pass to discover missing relationships")

        # Get all canonical entities from context
        canonical_entities_str = context.get("canonical_entities", "[]")
        try:
            canonical_entities = json.loads(canonical_entities_str)
        except Exception as e:
            LOGGER.error(f"Failed to parse canonical entities for synthesis: {e}")
            return []

        if not canonical_entities:
            LOGGER.warning("No canonical entities found for cross-batch synthesis")
            return []

        # Organize entities by type for better LLM comprehension
        entities_by_type = {}
        for entity in canonical_entities:
            entity_type = entity.get("entity_type", "Unknown")
            if entity_type not in entities_by_type:
                entities_by_type[entity_type] = []
            entities_by_type[entity_type].append(entity)

        # Organize existing relationships by batch for analysis
        relationships_by_batch = {}
        for rel in existing_relationships:
            batch_name = rel.get("attributes", {}).get("extraction_batch", "unknown")
            if batch_name not in relationships_by_batch:
                relationships_by_batch[batch_name] = []
            relationships_by_batch[batch_name].append({
                "source": rel.get("source_entity_id") or rel.get("source_canonical_id"),
                "target": rel.get("target_entity_id") or rel.get("target_canonical_id"),
                "type": rel.get("type") or rel.get("relationship_type")
            })

        # Build synthesis prompt
        synthesis_prompt = self._build_synthesis_prompt(
            entities_by_type=entities_by_type,
            relationships_by_batch=relationships_by_batch,
            semantic_batches=semantic_batches
        )

        # Execute synthesis LLM call
        try:
            cross_batch_rels = await self._execute_llm_call(synthesis_prompt)

            # Tag these relationships as cross-batch synthesis
            for rel in cross_batch_rels:
                if "attributes" not in rel:
                    rel["attributes"] = {}
                rel["attributes"]["extraction_batch"] = "cross_batch_synthesis"
                rel["attributes"]["synthesis_pass"] = True

            LOGGER.info(
                f"Cross-batch synthesis discovered {len(cross_batch_rels)} relationships",
                extra={"cross_batch_count": len(cross_batch_rels)}
            )

            return cross_batch_rels

        except Exception as e:
            LOGGER.error(f"Cross-batch synthesis LLM call failed: {e}", exc_info=True)
            return []

    def _build_synthesis_prompt(
        self,
        entities_by_type: Dict[str, List[Dict[str, Any]]],
        relationships_by_batch: Dict[str, List[Dict[str, Any]]],
        semantic_batches: List[Dict[str, Any]]
    ) -> str:
        """Build the prompt for cross-batch relationship synthesis.

        Args:
            entities_by_type: All canonical entities organized by type
            relationships_by_batch: Existing relationships grouped by extraction batch
            semantic_batches: List of semantic batch configurations

        Returns:
            Formatted prompt string for LLM
        """
        # Build entities by type section
        entities_section = ""
        for entity_type, entities in sorted(entities_by_type.items()):
            entities_section += f"\n#### {entity_type} ({len(entities)} entities)\n"
            for entity in entities[:20]:  # Limit to first 20 per type to avoid token bloat
                entity_id = entity.get("canonical_id") or entity.get("id")
                name = entity.get("name") or entity.get("title") or entity.get("term") or "N/A"
                entities_section += f"- ID: {entity_id}, Name: {name}\n"
            if len(entities) > 20:
                entities_section += f"  ... and {len(entities) - 20} more\n"

        # Build semantic batches section
        batches_section = ""
        for batch in semantic_batches:
            batch_name = batch.get("name", "unknown")
            description = batch.get("description", "")
            sections = batch.get("sections", [])
            expected_rels = batch.get("expected_rels", [])
            batches_section += f"\n#### {batch_name}: {description}\n"
            batches_section += f"- Sections: {', '.join(sections)}\n"
            batches_section += f"- Expected relationships: {', '.join(expected_rels)}\n"

        # Build existing relationships section
        relationships_section = ""
        for batch_name, rels in sorted(relationships_by_batch.items()):
            relationships_section += f"\n#### Batch: {batch_name} ({len(rels)} relationships)\n"
            # Show a sample of relationships
            for rel in rels[:10]:  # Limit sample
                relationships_section += f"- {rel['source']} --[{rel['type']}]--> {rel['target']}\n"
            if len(rels) > 10:
                relationships_section += f"  ... and {len(rels) - 10} more\n"

        # Format the imported template with the dynamic content
        return CROSS_BATCH_SYNTHESIS_PROMPT_TEMPLATE.format(
            entities_by_type=entities_section,
            semantic_batches_info=batches_section,
            existing_relationships=relationships_section
        )

    def _build_batch_user_message(self, context: Dict[str, Any], batch: Dict[str, Any]) -> str:
        """Build user message for a semantic batch with multiple related sections.

        This method handles batches that may contain multiple sections (e.g., declarations + coverages)
        to enable extraction of cross-section relationships.

        Args:
            context: Global context with all entities
            batch: Batch configuration with sections, chunks, and routed table data

        Returns:
            Formatted user prompt for the LLM
        """
        batch_name = batch.get("name", "unknown")
        batch_description = batch.get("description", "")
        sections = batch.get("sections", [])
        expected_rels = batch.get("expected_rels", [])

        # Format multi-section content
        batch_chunks_text = ""
        if len(sections) == 1:
            # Single section batch
            section_name = sections[0].replace("_", " ").title()
            batch_chunks_text += f"### Section: {section_name}\n"
        else:
            # Multi-section batch
            batch_chunks_text += f"### Batch: {batch_description}\n"
            batch_chunks_text += f"### Sections included: {', '.join([s.replace('_', ' ').title() for s in sections])}\n\n"

        # Group chunks by section for clarity
        chunks_by_section = {}
        for chunk in batch.get("chunks", []):
            section_key = chunk.get("section_type", "unknown")
            if section_key not in chunks_by_section:
                chunks_by_section[section_key] = []
            chunks_by_section[section_key].append(chunk)

        # Format each section's content
        for section_key in sections:
            if section_key not in chunks_by_section:
                continue

            section_name = section_key.replace("_", " ").title()
            section_chunks = chunks_by_section[section_key]

            batch_chunks_text += f"\n## {section_name} Section\n"
            for chunk in section_chunks:
                chunk_text = chunk.get('text', '')
                # Limit chunk text to 2000 chars to avoid token explosion
                if len(chunk_text) > 2000:
                    chunk_text = chunk_text[:2000] + "\n... (truncated)"
                batch_chunks_text += f"\n[Chunk {chunk['chunk_id'][:8]}...]\n"
                batch_chunks_text += chunk_text
                batch_chunks_text += "\n"

        # Simplified entity summary for the batch
        entities = json.loads(context['entities_json'])
        entity_summary = {}
        for entity in entities:
            etype = entity.get('entity_type', 'Unknown')
            entity_summary[etype] = entity_summary.get(etype, 0) + 1

        entity_breakdown = "\n".join([f"  • {etype}: {count}" for etype, count in sorted(entity_summary.items())])

        # Get routed table data (already as JSON strings from _call_llm_api)
        sov_json = batch.get("sov_items_json", "[]")
        loss_run_json = batch.get("loss_run_claims_json", "[]")
        tables_json = batch.get("document_tables_json", "[]")

        # Count items for display
        try:
            sov_count = len(json.loads(sov_json))
            loss_run_count = len(json.loads(loss_run_json))
            tables_count = len(json.loads(tables_json))
        except:
            sov_count = 0
            loss_run_count = 0
            tables_count = 0

        # Build expected relationships hint
        expected_rels_str = ", ".join(expected_rels) if expected_rels else "any valid relationships"

        user_message = f"""
Extract relationships from this {context['document_type']} document.

BATCH CONTEXT: {batch_description}
You are analyzing a semantically grouped batch containing MULTIPLE SECTIONS that commonly have cross-section relationships.
This allows you to see both sides of relationships (e.g., Policy in declarations + Coverage in coverages).

Sections in this batch: {', '.join([s.replace('_', ' ').title() for s in sections])}
Expected relationship types: {expected_rels_str}

Entity Summary ({len(entities)} total available for linking):
{entity_breakdown}

CANONICAL ENTITIES (deduplicated, normalized)
{context['entities_json']}

SECTION CONTENT (Multi-section batch - look for cross-section links!)
{batch_chunks_text}

TABLE DATA (Routed to this batch only)
SOV Items ({sov_count} items):
{sov_json}

Loss Run Claims ({loss_run_count} claims):
{loss_run_json}

Document Tables ({tables_count} tables):
{tables_json}

RELATIONSHIP EXTRACTION STRATEGY:
1. **Cross-Section Awareness**: Look for relationships ACROSS the sections provided above.
   - Example: Policy entity in declarations + Coverage entity in coverages → HAS_COVERAGE relationship
   - Example: Coverage entity in coverages + Condition entity in conditions → SUBJECT_TO relationship
   - Example: Policy in declarations + Exclusion in exclusions → EXCLUDES relationship
   - Example: Coverage in coverages + Exclusion in exclusions → EXCLUDES relationship
   - Example: Coverage in coverages + Definition in definitions → DEFINED_IN relationship
   - Example: Policy in declarations + Location in SOV → HAS_LOCATION relationship
   - Example: Policy in declarations + Claim in loss runs → HAS_CLAIM relationship
   - Example: Endorsement + Coverage → MODIFIED_BY relationship

2. **Contextual Relationship Discovery**: Beyond expected types, identify ALL valid relationships present.
   - **Policy Hub Relationships**: Policies connect to coverages, insureds, locations, claims, endorsements, exclusions, conditions
   - **Coverage Relationships**: Coverages connect to conditions, exclusions, definitions, limits, deductibles, endorsements, locations
   - **Exclusion Relationships**: Exclusions apply to coverages or policies, may reference definitions
   - **Condition Relationships**: Conditions apply to coverages or policies
   - **Endorsement Relationships**: Endorsements modify coverages or policies
   - **Location Relationships**: Locations have coverages, are referenced in claims
   - **Claim Relationships**: Claims relate to coverages, locations, vehicles, drivers
   - **Definition Relationships**: Definitions are referenced by coverages, exclusions, conditions

3. **Focus on Expected Types**: Prioritize extracting {expected_rels_str} from this batch, but don't limit yourself to these.

4. **Use Routed Table Data**: The table data above has been specifically routed to this batch as it's relevant.
   - Match entities to table rows by IDs, addresses, claim numbers, etc.
   - Table evidence is high-confidence (0.85-0.95)

5. **Evidence Requirements**: Each relationship MUST have evidence (text quote OR table reference).

6. **Confidence Scoring**:
   - 0.90-1.00: Explicit labeled phrase or table match
   - 0.70-0.89: Strong implicit or multi-chunk corroboration
   - 0.45-0.69: Use as CANDIDATE instead

7. **Completeness**: Extract ALL valid relationships you can find in this batch, not just a sample.

EXPECTED OUTPUT
Return ONLY valid JSON following the schema.
NO markdown backticks, NO explanations, JUST the JSON object.
"""
        return user_message

    
    def _parse_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM response.
        
        Args:
            llm_response: Raw LLM response
            
        Returns:
            Parsed dictionary
        """
        parsed = parse_json_safely(llm_response)
        
        if parsed is None:
             LOGGER.error(
                 f"Failed to parse LLM response",
                 extra={"llm_response_snippet": llm_response[:1000] if llm_response else "Empty"}
             )
             # Log full response for debugging
             LOGGER.debug(f"Full failed LLM response: {llm_response}")
             return {"relationships": []}
             
        return parsed
    
    async def _create_relationship(
        self,
        document_id: UUID,
        relationship_data: Dict[str, Any],
        canonical_entities: List[CanonicalEntity],
        chunks: Optional[List[DocumentChunk]] = None,
        workflow_id: Optional[UUID] = None
    ) -> Optional[EntityRelationship]:
        """Create EntityRelationship record with flexible entity matching.
        
        Args:
            document_id: Document ID
            relationship_data: Relationship data from LLM
            canonical_entities: List of canonical entities
            chunks: Optional chunks for temp entity reconciliation
            workflow_id: ID of the workflow
            
        Returns:
            Created relationship or None if invalid
        """
        # Validate relationship type - Handle multiple possible keys from LLM
        rel_type = relationship_data.get("type") or relationship_data.get("relationship_type")
        
        if not rel_type:
            LOGGER.warning(
                f"Missing relationship type in LLM response",
                extra={"relationship_data": relationship_data}
            )
            return None

        if rel_type not in VALID_RELATIONSHIP_TYPES:
            LOGGER.warning(
                f"Invalid relationship type: {rel_type}",
                extra={
                    "valid_types": list(VALID_RELATIONSHIP_TYPES),
                    "relationship_data": relationship_data
                }
            )
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
        
        # Create relationship
        rel_id = relationship_data.get("id") or relationship_data.get("relationship_id")
        
        # Build attributes
        attributes = relationship_data.get("attributes", {})
        if "evidence" not in attributes:
            attributes["evidence"] = relationship_data.get("evidence", [])
        
        # Add table data references if present in evidence
        for ev in attributes["evidence"]:
            if isinstance(ev, dict):
                if "sov_id" in ev:
                    attributes["sov_reference"] = ev.get("sov_id")
                if "claim_id" in ev:
                    attributes["claim_reference"] = ev.get("claim_id")

        relationship = EntityRelationship(
            document_id=document_id,
            source_entity_id=source_entity.id,
            target_entity_id=target_entity.id,
            relationship_type=rel_type,
            confidence=relationship_data.get("confidence", 0.8),
            attributes=attributes
        )
        
        # If rel_id is provided, try to use it (must be valid UUID or we let it be)
        if rel_id:
            try:
                relationship.id = UUID(rel_id)
            except (ValueError, AttributeError):
                # If not a valid UUID, let SQLAlchemy generate one
                pass
        
        self.session.add(relationship)
        await self.session.flush() # Ensure ID is generated
        
        # Add to workflow scope if provided
        if workflow_id:
            from app.repositories.entity_repository import EntityRelationshipRepository
            rel_repo = EntityRelationshipRepository(self.session)
            await rel_repo.add_to_workflow_scope(workflow_id, relationship.id)
            
        LOGGER.info(
            f"Created relationship: {source_entity.entity_type}({source_entity.canonical_key[:8]}) "
            f"--{rel_type}--> {target_entity.entity_type}({target_entity.canonical_key[:8]})"
        )
        
        return relationship
    
    def _find_entity(
        self,
        entity_identifier: str,
        canonical_entities: List[CanonicalEntity],
        chunks: Optional[List[DocumentChunk]] = None
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
                
        # Strategy 1b: Match by stable ID in attributes (id is now stored in attributes by resolver)
        for entity in canonical_entities:
            if entity.attributes:
                # Check for 'id' attribute which we now capture
                if entity.attributes.get("id") == entity_identifier:
                    return entity
                # Check for 'entity_id' fallback
                if entity.attributes.get("entity_id") == entity_identifier:
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

    def _build_user_message(self, context: dict) -> str:
        """Build improved user message for relationship extraction."""
        
        # Parse entities to analyze
        entities = json.loads(context['entities_json'])
        entity_summary = {}
        for entity in entities:
            etype = entity.get('entity_type', 'Unknown')
            entity_summary[etype] = entity_summary.get(etype, 0) + 1
        
        # Build entity type summary
        entity_breakdown = "\n".join([f"  • {etype}: {count}" for etype, count in sorted(entity_summary.items())])
        
        # Build section priority list
        section_summary = context.get('section_summary', {})
        priority_sections = ["declarations", "coverages", "conditions", "sov", "endorsements", "definitions"]
        available_sections = [s for s in priority_sections if s in section_summary]
        
        user_message = f"""
            Extract relationships from this {context['document_type']} document.

            Entity Summary ({len(entities)} total):
            {entity_breakdown}

            Sections Available: {', '.join(available_sections)}

            CANONICAL ENTITIES (deduplicated, normalized)
            {context['entities_json']}

            DOCUMENT SECTIONS (super-chunk format, ordered by priority)
            {context['chunks_by_section']}

            TABLE DATA

            SOV Items ({context.get('sov_items_count', 0)} locations):
            {context.get('sov_items_json', '[]')}

            Loss Run Claims ({context.get('loss_run_claims_count', 0)} claims):
            {context.get('loss_run_claims_json', '[]')}

            Document Tables ({context.get('document_tables_count', 0)} tables):
            {context.get('document_tables_json', '[]')}

            RELATIONSHIP EXTRACTION STRATEGY

            PRIORITY 1 - Policy Core Relationships (declarations section):
            • Find Policy entity (entity_type="Policy")
            • Extract: ISSUED_BY (carrier), HAS_INSURED (insured org), BROKERED_BY (broker)
            • Look for explicit phrases: "issued by", "insured:", "broker:"

            PRIORITY 2 - Coverage Relationships (coverages section):
            • Find Coverage entities (entity_type="Coverage")
            • Extract: Policy HAS_COVERAGE Coverage
            • Each coverage mention in coverages section = relationship

            PRIORITY 3 - Location Relationships (sov section + SOV table):
            • Match Location entities with SOV items by address/location_id
            • Extract: Policy HAS_LOCATION Location
            • Use table data as primary evidence

            PRIORITY 4 - Condition/Definition Relationships:
            • Condition entities → Coverage SUBJECT_TO Condition
            • Definition entities → Coverage/Condition DEFINED_IN Definition

            PRIORITY 5 - Endorsement Relationships:
            • Endorsement entities → Policy MODIFIED_BY Endorsement

            PRIORITY 6 - Claim Relationships (loss_runs section + table):
            • Match Claim entities with loss run table by claim_number
            • Extract: Policy HAS_CLAIM Claim

            COMMON PATTERNS TO EXTRACT

            Pattern 1: Policy Issuance
            Text: "Policy No. X issued by Y Insurance Company"
            → Policy(X) --ISSUED_BY--> Organization(Y)

            Pattern 2: Insured Organization
            Text: "Named Insured: ABC Corporation"
            → Policy --HAS_INSURED--> Organization(ABC Corporation)

            Pattern 3: Coverage Listing
            Text: In coverages section, entity "Equipment Breakdown" appears
            → Policy --HAS_COVERAGE--> Coverage(Equipment Breakdown)

            Pattern 4: Location from SOV
            SOV row: location_id=1, address="123 Main St"
            Entity: Location with matching address
            → Policy --HAS_LOCATION--> Location(123 Main St)

            Pattern 5: Broker
            Text: "Broker: XYZ Insurance Brokers"
            → Policy --BROKERED_BY--> Organization(XYZ Insurance Brokers)

            Pattern 6: Condition Application
            Text: In conditions section, "Coinsurance" condition
            Entity: Coverage "Property"
            → Coverage(Property) --SUBJECT_TO--> Condition(Coinsurance)

            EXPECTED OUTPUT

            For this document with {len(entities)} entities, extract:
            • AT LEAST {min(len([e for e in entities if e.get('entity_type') == 'Coverage']), 10)} HAS_COVERAGE relationships
            • AT LEAST {min(len([e for e in entities if e.get('entity_type') == 'Location']), 4)} HAS_LOCATION relationships
            • AT LEAST 3-5 policy-level relationships (ISSUED_BY, HAS_INSURED, BROKERED_BY)
            • Condition/Definition relationships where applicable

            Return ONLY valid JSON following the schema.
            NO markdown backticks, NO explanations, JUST the JSON object.
            """
        
        return user_message

    
    def _reconcile_temp_entity(
        self,
        temp_id: str,
        canonical_entities: List[CanonicalEntity],
        chunks: List[DocumentChunk]
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
