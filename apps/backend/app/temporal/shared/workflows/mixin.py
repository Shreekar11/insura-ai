"""Mixin for shared document processing logic."""

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from temporalio import workflow
from temporalio.common import RetryPolicy

from app.schemas.product.shared_workflow_schemas import (
    PageAnalysisOutputSchema,
    OCRExtractionOutputSchema,
    TableExtractionOutputSchema,
    HybridChunkingOutputSchema,
    ExtractionOutputSchema,
    EntityResolutionOutputSchema,
    IndexingOutputSchema,
    validate_workflow_output,
)


class DocumentProcessingConfig(BaseModel):
    """Configuration for document processing pipeline."""
    workflow_id: str
    workflow_name: Optional[str] = None
    target_sections: Optional[List[str]] = None
    target_entities: Optional[List[str]] = None
    skip_processed: bool = False
    skip_extraction: bool = False
    skip_enrichment: bool = False
    skip_indexing: bool = False
    document_name: Optional[str] = None


class DocumentProcessingMixin:
    """Mixin class providing document processing methods to workflows."""

    async def process_document(
        self, 
        document_id: str, 
        config: DocumentProcessingConfig
    ) -> Dict[str, Any]:
        """Main orchestrator method for processing a single document."""
        results = {}
        document_profile = None

        # 1. Processed Stage (OCR, Page Analysis, Tables, Chunking)
        if not config.skip_processed:
            processed_result = await self._execute_processed_stage(
                config.workflow_id, 
                document_id, 
                config.target_sections,
                config.workflow_name,
                config.document_name
            )
            results["processed"] = processed_result
            document_profile = processed_result.get("document_profile")

        # 2. Extraction Stage
        if not config.skip_extraction:
            # We need document_profile for extraction
            if not document_profile:
                document_profile = await workflow.execute_activity(
                    "get_document_profile_activity",
                    args=[document_id],
                    start_to_close_timeout=timedelta(seconds=30),
                )
            
            extraction_result = await self._execute_extraction_stage(
                config.workflow_id,
                document_id,
                document_profile,
                config.target_sections,
                config.target_entities,
                config.document_name
            )
            results["extracted"] = extraction_result

        # 3. Enrichment Stage
        if not config.skip_enrichment:
            effective_coverages = results.get("extracted", {}).get("effective_coverages", [])
            effective_exclusions = results.get("extracted", {}).get("effective_exclusions", [])
            
            enrichment_result = await self._execute_enrichment_stage(
                config.workflow_id,
                document_id,
                config.document_name,
                effective_coverages=effective_coverages,
                effective_exclusions=effective_exclusions,
            )
            results["enriched"] = enrichment_result

        # 4. Indexing Stage (includes citation creation after chunk embeddings)
        if not config.skip_indexing:
            effective_coverages = results.get("extracted", {}).get("effective_coverages", [])
            effective_exclusions = results.get("extracted", {}).get("effective_exclusions", [])
            indexing_result = await self._execute_indexing_stage(
                config.workflow_id,
                document_id,
                config.target_sections,
                config.document_name,
                effective_coverages=effective_coverages,
                effective_exclusions=effective_exclusions,
            )
            results["summarized"] = indexing_result

        return results

    async def _execute_processed_stage(
        self,
        workflow_id: str,
        document_id: str,
        target_sections: Optional[List[str]] = None,
        workflow_name: Optional[str] = None,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute OCR, Page Analysis, Table Extraction, and Chunking."""
        workflow.logger.info(f"Starting ProcessedStage for {document_id}")

        doc_label = document_name or document_id

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "processed", "running", None, {"document_name": document_name}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # OCR Extraction
        ocr_data = await workflow.execute_activity(
            "extract_ocr",
            args=[workflow_id, document_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=60),
                backoff_coefficient=2.0,
            ),
        )

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "processed", "completed", None, {"document_name": document_name}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "classified", "running", None, {"document_name": document_name}],
            start_to_close_timeout=timedelta(seconds=30),
        )
        ocr_output = validate_workflow_output(
            {
                "document_id": ocr_data.get('document_id'),
                "page_count": ocr_data.get('page_count', 0),
                "pages_processed": ocr_data.get('pages_processed', []),
                "selective": False,
                "has_section_metadata": False,
                "section_distribution": None,
            },
            OCRExtractionOutputSchema,
            "DocumentProcessingMixin.ocr"
        )

        # Page Analysis
        page_signals = await workflow.execute_activity(
            "extract_page_signals",
            args=[document_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        
        classifications = await workflow.execute_activity(
            "classify_pages",
            args=[document_id, page_signals],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        
        manifest = await workflow.execute_activity(
            "create_page_manifest",
            args=[document_id, classifications, workflow_name],
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=5),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
            ),
        )
        page_manifest = validate_workflow_output(
            manifest,
            PageAnalysisOutputSchema,
            "DocumentProcessingMixin.page_analysis"
        )
        
        document_profile = page_manifest.get('document_profile', {})
        page_section_map = page_manifest.get('page_section_map')
        pages_to_process = page_manifest.get('pages_to_process', [])
        section_boundaries = document_profile.get('section_boundaries', [])

        # Table Extraction
        table_result = await workflow.execute_activity(
            "extract_tables",
            args=[workflow_id, document_id, None, pages_to_process],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3
            )
        )
        table_output = validate_workflow_output(
            table_result,
            TableExtractionOutputSchema,
            "DocumentProcessingMixin.table_extraction"
        )

        # Hybrid Chunking
        chunking_result = await workflow.execute_activity(
            "perform_hybrid_chunking",
            args=[workflow_id, document_id, page_section_map, target_sections, section_boundaries],
            start_to_close_timeout=timedelta(minutes=15),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )
        chunking_output = validate_workflow_output(
            {
                "chunk_count": chunking_result["chunk_count"],
                "super_chunk_count": chunking_result["super_chunk_count"],
                "sections_detected": chunking_result["sections_detected"],
                "section_stats": chunking_result["section_stats"],
                "total_tokens": chunking_result["total_tokens"],
                "avg_tokens_per_chunk": chunking_result["avg_tokens_per_chunk"],
                "section_source": chunking_result.get("section_source", "unknown"),
            },
            HybridChunkingOutputSchema,
            "DocumentProcessingMixin.chunking"
        )

        processed_metadata = {
            "page_count": len(pages_to_process),
            "table_count": table_output.get("tables_found", 0),
            "chunk_count": chunking_output.get("chunk_count", 0),
            "document_profile": document_profile,
            "document_name": document_name,
        }

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "classified", "completed", None, processed_metadata],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {
            "stage": "processed",
            "status": "completed",
            "workflow_id": workflow_id,
            "document_id": document_id,
            "document_type": document_profile.get("document_type"),
            "pages_processed": len(pages_to_process),
            "tables_found": table_output.get("tables_found", 0),
            "chunks_created": chunking_output.get("chunk_count", 0),
            "document_profile": document_profile,
            "classified": True,
        }

    async def _execute_extraction_stage(
        self,
        workflow_id: str,
        document_id: str,
        document_profile: Dict[str, Any],
        target_sections: Optional[List[str]] = None,
        target_entities: Optional[List[str]] = None,
        document_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute LLM extraction."""
        workflow.logger.info(f"Starting ExtractedStage for {document_id}")

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "running", None, {"document_name": document_name}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        extraction_result = await workflow.execute_activity(
            "extract_section_fields",
            args=[workflow_id, document_id, target_sections, target_entities],
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3,
            ),
        )

        # Convert profile for output schema validation if needed (matches original child workflow logic)
        classification_result = {
            "document_id": document_profile.get("document_id"),
            "document_type": document_profile.get("document_type", "unknown"),
            "document_subtype": document_profile.get("document_subtype"),
            "confidence": document_profile.get("confidence", 0.0),
            "section_boundaries": document_profile.get("section_boundaries", []),
            "page_section_map": document_profile.get("page_section_map", {}),
            "metadata": {
                **document_profile.get("metadata", {}),
                "source": "phase0_manifest",
            },
        }

        output = validate_workflow_output(
            {
                "classification": classification_result,
                "extraction": extraction_result,
                "document_type": classification_result["document_type"],
                "total_entities": len(extraction_result.get('all_entities', [])),
                "total_llm_calls": len(extraction_result.get('section_results', [])),
            },
            ExtractionOutputSchema,
            "DocumentProcessingMixin.extraction"
        )

        # Calculate section_count based on synthesized sections (coverages + exclusions)
        # This reflects the coverage-centric output model where endorsements are
        # projected into coverage and exclusion sections
        effective_coverages = extraction_result.get("effective_coverages", [])
        effective_exclusions = extraction_result.get("effective_exclusions", [])
        synthesized_section_count = (
            (1 if effective_coverages else 0) +
            (1 if effective_exclusions else 0)
        )

        extraction_metadata = {
            "section_count": synthesized_section_count if synthesized_section_count > 0 else len(extraction_result.get("section_results", [])),
            "entity_count": output.get("total_entities", 0),
            "document_name": document_name,
        }

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "extracted", "completed", None, extraction_metadata],
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {
            "stage": "extracted",
            "status": "completed",
            "workflow_id": workflow_id,
            "document_id": document_id,
            "sections_extracted": extraction_metadata["section_count"],
            "entities_found": output.get("total_entities", 0),
            "effective_coverages": effective_coverages,
            "effective_exclusions": effective_exclusions,
        }

    async def _execute_enrichment_stage(
        self,
        workflow_id: str,
        document_id: str,
        document_name: Optional[str] = None,
        effective_coverages: Optional[List[Dict[str, Any]]] = None,
        effective_exclusions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute entity resolution and relationship extraction."""
        workflow.logger.info(f"Starting EnrichedStage for {document_id}")

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "enriched", "running", None, {"document_name": document_name}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        entity_ids = []
        try:
            # Prepare rich context for enrichment
            rich_context = {
                "effective_coverages": effective_coverages,
                "effective_exclusions": effective_exclusions
            }
            
            aggregated = await workflow.execute_activity(
                "aggregate_document_entities",
                args=[workflow_id, document_id, rich_context],
                start_to_close_timeout=timedelta(minutes=5),
            )
            
            entity_ids = await workflow.execute_activity(
                "resolve_canonical_entities",
                args=[workflow_id, document_id, aggregated],
                start_to_close_timeout=timedelta(minutes=3),
            )
            
            relationships = await workflow.execute_activity(
                "extract_relationships",
                args=[workflow_id, document_id],
                start_to_close_timeout=timedelta(minutes=10),
            )
            
            output = validate_workflow_output(
                {
                    "entity_count": len(entity_ids),
                    "relationship_count": len(relationships),
                },
                EntityResolutionOutputSchema,
                "DocumentProcessingMixin.enrichment"
            )

            enrichment_metadata = {
                "entity_count": output.get("entity_count", 0),
                "relationship_count": output.get("relationship_count", 0),
                "document_name": document_name,
            }

            await workflow.execute_activity(
                "update_stage_status",
                args=[workflow_id, document_id, "enriched", "completed", None, enrichment_metadata],
                start_to_close_timeout=timedelta(seconds=30),
            )

            return {
                "stage": "enriched",
                "status": "completed",
                "workflow_id": workflow_id,
                "document_id": document_id,
                "entities_resolved": output.get("entity_count", 0),
                "relationships_extracted": output.get("relationship_count", 0),
            }

        except Exception as e:
            if entity_ids:
                await workflow.execute_activity(
                    "rollback_entities",
                    args=[entity_ids],
                    start_to_close_timeout=timedelta(minutes=1),
                )
            raise

    async def _execute_indexing_stage(
        self,
        workflow_id: str,
        document_id: str,
        target_sections: Optional[List[str]] = None,
        document_name: Optional[str] = None,
        effective_coverages: Optional[List[Dict[str, Any]]] = None,
        effective_exclusions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute vector indexing, graph construction, and citation creation."""
        workflow.logger.info(f"Starting SummarizedStage (Indexing) for {document_id}")

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "running", None, {"document_name": document_name}],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Run entity embeddings and chunk embeddings in parallel
        vector_indexing_handle = workflow.start_activity(
            "generate_embeddings_activity",
            args=[document_id, workflow_id, target_sections],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3
            )
        )

        chunk_embedding_handle = workflow.start_activity(
            "generate_chunk_embeddings_activity",
            args=[document_id, workflow_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3
            )
        )

        vector_indexing_result = await vector_indexing_handle
        chunk_embedding_result = await chunk_embedding_handle

        # Create citations after chunk embeddings so Tier 2 semantic search
        citation_result = {}
        if effective_coverages or effective_exclusions:
            try:
                citation_result = await workflow.execute_activity(
                    "create_citations_activity",
                    args=[document_id, effective_coverages or [], effective_exclusions or []],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=RetryPolicy(
                        initial_interval=timedelta(seconds=5),
                        maximum_attempts=3
                    ),
                )
            except Exception as e:
                workflow.logger.warning(f"Citation creation failed for {document_id}: {e}")

        graph_construction_result = await workflow.execute_activity(
            "construct_knowledge_graph_activity",
            args=[document_id, workflow_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                maximum_attempts=3
            )
        )

        total_chunks_indexed = (
            vector_indexing_result.get("chunks_embedded", 0) +
            chunk_embedding_result.get("chunks_embedded", 0)
        )

        output = validate_workflow_output(
            {
                "workflow_id": workflow_id,
                "document_id": document_id,
                "vector_indexed": True,
                "graph_constructed": True,
                "chunks_indexed": total_chunks_indexed,
                "entities_created": graph_construction_result.get("entities_created", 0),
                "relationships_created": graph_construction_result.get("relationships_created", 0),
                "embeddings_linked": graph_construction_result.get("embeddings_linked", 0),
            },
            IndexingOutputSchema,
            "DocumentProcessingMixin.indexing"
        )

        indexing_metadata = {
            "chunks_indexed": output.get("chunks_indexed", 0),
            "chunk_embeddings": chunk_embedding_result.get("chunks_embedded", 0),
            "entities_created": output.get("entities_created", 0),
            "relationships_created": output.get("relationships_created", 0),
            "document_name": document_name,
        }

        await workflow.execute_activity(
            "update_stage_status",
            args=[workflow_id, document_id, "summarized", "completed", None, indexing_metadata],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return {
            "stage": "summarized",
            "status": "completed",
            "document_id": document_id,
            "summarized": True,
            "indexed": True,
            "chunks_indexed": output.get("chunks_indexed", 0),
        }
