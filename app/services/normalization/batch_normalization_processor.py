"""Batch processing integration for normalization service.

This module provides batch processing methods that integrate the BatchExtractor
with the normalization service, enabling optimized pipeline execution.
"""

from typing import List, Dict, Any, Tuple, Optional
from uuid import UUID, uuid4
import hashlib

from app.models.page_data import PageData
from app.services.extraction.batch_extractor import BatchExtractor
from app.services.extraction.batch_processor import BatchProcessor
from app.services.normalization.semantic_normalizer import SemanticNormalizer
from app.services.chunking.chunking_service import ChunkingService
from app.services.extraction.entity_resolver import EntityResolver
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.normalization_repository import NormalizationRepository
from app.repositories.classification_repository import ClassificationRepository
from app.utils.logging import get_logger
from app.config import settings
from app.services.classification.constants import DOCUMENT_TYPES

LOGGER = get_logger(__name__)


class BatchNormalizationProcessor:
    """Handles batch processing for the normalization pipeline.
    
    This class orchestrates the unified batch extraction process,
    integrating with existing repositories and services.
    """
    
    def __init__(
        self,
        unified_extractor: BatchExtractor,
        semantic_normalizer: SemanticNormalizer,
        chunking_service: ChunkingService,
        entity_resolver: Optional[EntityResolver],
        chunk_repository: ChunkRepository,
        normalization_repository: NormalizationRepository,
        classification_repository: ClassificationRepository,
    ):
        """Initialize batch normalization processor.
        
        Args:
            unified_extractor: Batch extractor instance
            semantic_normalizer: Semantic normalizer for field-level accuracy
            chunking_service: Service for chunking documents
            entity_resolver: Entity resolver for canonical entity mapping
            chunk_repository: Repository for chunk operations
            normalization_repository: Repository for normalization operations
            classification_repository: Repository for classification operations
        """
        self.unified_extractor = unified_extractor
        self.semantic_normalizer = semantic_normalizer
        self.chunking_service = chunking_service
        self.entity_resolver = entity_resolver
        self.chunk_repository = chunk_repository
        self.normalization_repository = normalization_repository
        self.classification_repository = classification_repository
    
    async def process_pages_in_batches(
        self,
        pages: List[PageData],
        document_id: UUID,
        batch_size: int = 3
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Process pages using unified batch extraction.
        
        This method replaces the sequential chunk processing with batched
        processing, reducing LLM calls by 75-85%.
        
        Args:
            pages: List of PageData objects
            document_id: Document UUID
            batch_size: Number of chunks per batch (default: 3)
            
        Returns:
            Tuple of (merged_normalized_text, classification_result)
        """
        if not pages:
            LOGGER.warning("Empty pages list provided")
            return "", None
        
        pipeline_run_id = str(uuid4())
        
        LOGGER.info(
            "Starting batch normalization pipeline",
            extra={
                "document_id": str(document_id),
                "total_pages": len(pages),
                "batch_size": batch_size,
                "pipeline_run_id": pipeline_run_id
            }
        )
        
        # Step 1: Chunk pages
        all_chunks = []
        for page in pages:
            page_text = page.get_content(prefer_markdown=True)
            if not page_text or not page_text.strip():
                continue
            
            page_chunks = self.chunking_service.chunk_document(
                text=page_text,
                document_id=document_id,
                initial_page_number=page.page_number
            )
            
            for chunk in page_chunks:
                chunk.metadata.page_number = page.page_number
                chunk.metadata.stable_chunk_id = self._generate_stable_chunk_id(
                    document_id=document_id,
                    page_number=page.page_number,
                    chunk_index=chunk.metadata.chunk_index
                )
                all_chunks.append(chunk)
        
        LOGGER.info(f"Created {len(all_chunks)} chunks from {len(pages)} pages")
        
        # Step 1.5: Clean up existing chunks for this document (if any)
        # This prevents unique constraint violations on stable_chunk_id
        try:
            existing_chunks = await self.chunk_repository.get_chunks_by_document(document_id)
            if existing_chunks:
                LOGGER.info(
                    f"Found {len(existing_chunks)} existing chunks for document, cleaning up...",
                    extra={"document_id": str(document_id)}
                )
                await self.chunk_repository.delete_chunks_by_document(document_id)
                LOGGER.info("Existing chunks deleted successfully")
        except Exception as e:
            LOGGER.warning(f"Failed to clean up existing chunks: {e}")
        
        # Step 2: Create document chunks in database (bulk)
        chunks_data = [
            {
                "document_id": document_id,
                "page_number": chunk.metadata.page_number,
                "chunk_index": chunk.metadata.chunk_index,
                "raw_text": chunk.text,
                "token_count": chunk.metadata.token_count,
                "section_name": chunk.metadata.section_name,
                "stable_chunk_id": chunk.metadata.stable_chunk_id,
                "section_type": None,  # Will be set by unified extractor
                "subsection_type": None,
            }
            for chunk in all_chunks
        ]
        
        db_chunks = await self.chunk_repository.bulk_create_chunks(chunks_data)
        
        # Map stable IDs to database chunks
        chunk_id_map = {
            chunk.metadata.stable_chunk_id: db_chunk
            for chunk, db_chunk in zip(all_chunks, db_chunks)
        }
        
        # Step 3: Process chunks in batches using unified extractor
        chunk_batches = BatchProcessor.create_batches(all_chunks, batch_size)
        
        all_batch_results = {}
        all_classification_signals = []
        
        for batch_idx, batch in enumerate(chunk_batches):
            LOGGER.info(f"Processing batch {batch_idx + 1}/{len(chunk_batches)}")
            
            # Prepare batch input for unified extractor
            batch_input = [
                {
                    "chunk_id": chunk.metadata.stable_chunk_id,
                    "text": chunk.text
                }
                for chunk in batch
            ]
            
            # Call unified extractor
            batch_results = await self.unified_extractor.extract_batch(
                chunks=batch_input,
                document_id=document_id
            )
            
            all_batch_results.update(batch_results)
            
            # Extract classification signals
            for chunk_id, result in batch_results.items():
                signals_payload = self._extract_signals(result)
                all_classification_signals.append({
                    "signals": signals_payload,
                    "section_type": result.get("section_type"),
                    "weight": result.get("section_confidence", 1.0) or 1.0,
                })
        
        # Step 4: Apply semantic normalization and persist results
        normalized_chunks_data = []
        normalized_texts = []
        
        for chunk in all_chunks:
            stable_id = chunk.metadata.stable_chunk_id
            batch_result = all_batch_results.get(stable_id)
            
            if not batch_result:
                LOGGER.warning(f"No batch result for chunk {stable_id}")
                continue
            
            # Apply semantic normalization for field-level accuracy
            semantic_result = self.semantic_normalizer.normalize_text_with_fields(
                batch_result["normalized_text"]
            )
            
            final_normalized_text = semantic_result["normalized_text"]
            extracted_fields = semantic_result["extracted_fields"]
            
            normalized_texts.append(final_normalized_text)
            
            # Get database chunk
            db_chunk = chunk_id_map.get(stable_id)
            if not db_chunk:
                LOGGER.error(f"Database chunk not found for {stable_id}")
                continue
            
            # Update database chunk with section info
            db_chunk.section_type = batch_result.get("section_type")
            
            # Prepare normalized chunk data
            normalized_chunks_data.append({
                "chunk_id": db_chunk.id,
                "normalized_text": final_normalized_text,
                "method": "unified_batch",
                "extracted_fields": extracted_fields,
                "entities": batch_result.get("entities", []),
                "model_version": self.unified_extractor.model,
                "prompt_version": "unified_v1.0",
                "pipeline_run_id": pipeline_run_id,
                "source_stage": "batch_normalization",
                "quality_score": self._calculate_quality_score(batch_result),
            })
            
            # Persist classification signals
            signals_payload = self._extract_signals(batch_result)
            await self.classification_repository.create_classification_signal(
                chunk_id=db_chunk.id,
                signals=signals_payload,
                model_name=self.unified_extractor.model,
                keywords=[],
                entities=batch_result.get("entities", []),
                confidence=self._get_signal_confidence(signals_payload),
            )
        
        # Bulk create normalized chunks
        normalized_chunks = await self.normalization_repository.bulk_create_normalized_chunks(
            normalized_chunks_data
        )
        
        LOGGER.info(
            f"Bulk created {len(normalized_chunks)} normalized chunks",
            extra={"document_id": str(document_id)}
        )
        
        # Step 5: Entity resolution (if enabled)
        if self.entity_resolver:
            for chunk_data, normalized_chunk in zip(normalized_chunks_data, normalized_chunks):
                entities = chunk_data.get("entities", [])
                if entities:
                    try:
                        await self.entity_resolver.resolve_entities_batch(
                            entities=entities,
                            chunk_id=normalized_chunk.id,
                            document_id=document_id
                        )
                        LOGGER.debug(
                            f"Resolved {len(entities)} entities for chunk {normalized_chunk.id}"
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"Entity resolution failed for chunk {normalized_chunk.id}: {e}",
                            exc_info=True
                        )
        
        # Step 6: Aggregate classification signals
        classification_result = self._aggregate_classification_signals(
            all_classification_signals
        )
        
        # Merge normalized texts
        merged_text = "\n\n".join(normalized_texts)
        
        LOGGER.info(
            "Batch normalization completed",
            extra={
                "document_id": str(document_id),
                "chunks_processed": len(normalized_chunks),
                "classified_type": classification_result.get("classified_type"),
                "confidence": classification_result.get("confidence"),
            }
        )
        
        return merged_text, classification_result
    
    def _generate_stable_chunk_id(
        self,
        document_id: UUID,
        page_number: int,
        chunk_index: int
    ) -> str:
        """Generate deterministic chunk ID."""
        return f"doc_{str(document_id)}_p{page_number}_c{chunk_index}"
    
    def _calculate_quality_score(self, batch_result: Dict[str, Any]) -> float:
        """Calculate quality score from batch result."""
        # Average entity confidence scores
        entities = batch_result.get("entities", [])
        if not entities:
            return 0.8  # Default score
        
        confidences = [e.get("confidence", 0.8) for e in entities]
        return sum(confidences) / len(confidences) if confidences else 0.8
    
    def _aggregate_classification_signals(
        self,
        signals_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aggregate classification signals from all chunks."""
        if not signals_list:
            return {
                "classified_type": "unknown",
                "confidence": 0.0,
                "method": "batch_aggregate",
                "all_scores": {doc_type: 0.0 for doc_type in DOCUMENT_TYPES},
            }
        
        aggregated_scores = {doc_type: 0.0 for doc_type in DOCUMENT_TYPES}
        total_weight = 0.0
        
        for signal_data in signals_list:
            signals = signal_data.get("signals", {})
            if not signals:
                continue
            weight = signal_data.get("weight", 1.0) or 1.0
            for doc_type in DOCUMENT_TYPES:
                aggregated_scores[doc_type] += signals.get(doc_type, 0.0) * weight
            total_weight += weight
        
        if total_weight == 0:
            return {
                "classified_type": "unknown",
                "confidence": 0.0,
                "method": "batch_aggregate",
                "all_scores": aggregated_scores,
            }
        
        normalized_scores = {
            doc_type: score / total_weight for doc_type, score in aggregated_scores.items()
        }
        classified_type = max(normalized_scores, key=normalized_scores.get)
        confidence = normalized_scores[classified_type]
        
        return {
            "classified_type": classified_type,
            "confidence": confidence,
            "method": "batch_aggregate",
            "all_scores": normalized_scores,
            "chunks_used": len(signals_list),
        }

    def _extract_signals(self, batch_result: Dict[str, Any]) -> Dict[str, float]:
        """Normalize signal payloads from different prompt versions."""
        raw_signals = batch_result.get("signals") or batch_result.get("classification_signals") or {}
        normalized = {}
        for doc_type in DOCUMENT_TYPES:
            value = None
            for key in (
                doc_type,
                doc_type.lower(),
                f"{doc_type}_signals",
                f"{doc_type.lower()}_signals",
            ):
                if key in raw_signals:
                    value = raw_signals[key]
                    break
            normalized[doc_type] = self._sanitize_signal_value(value)
        return normalized

    @staticmethod
    def _sanitize_signal_value(value: Any) -> float:
        """Coerce LLM signal outputs into a normalized float."""
        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            cleaned = value.strip()
            percent = False

            if cleaned.endswith("%"):
                cleaned = cleaned[:-1]
                percent = True

            cleaned = cleaned.replace(",", "")

            try:
                numeric = float(cleaned)
            except ValueError:
                return 0.0

            if percent:
                numeric /= 100.0
        else:
            return 0.0

        # Clamp to [0.0, 1.0]
        if numeric < 0:
            return 0.0
        if numeric > 1:
            return 1.0
        return numeric

    def _get_signal_confidence(self, signals: Dict[str, float]) -> float:
        """Return the strongest class score for a chunk."""
        return max(signals.values()) if signals else 0.0
