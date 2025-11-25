"""OCR normalization service for insurance document text cleaning.

This service implements comprehensive text normalization for OCR-extracted
insurance documents using a hybrid LLM + code approach:
- Stage 1: LLM-based structural cleanup (tables, hyphenation, OCR artifacts)
- Stage 2: Deterministic field normalization (dates, amounts, policy numbers)

It also maintains the legacy rule-based approach for backward compatibility.
"""

from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID, uuid4
import hashlib

from app.core.base_service import BaseService
from app.models.page_data import PageData
from app.services.normalization.llm_normalizer import LLMNormalizer
from app.services.normalization.semantic_normalizer import SemanticNormalizer
from app.services.chunking.chunking_service import ChunkingService
from app.services.classification.classification_service import ClassificationService
from app.services.classification.fallback_classifier import FallbackClassifier
from app.services.extraction.entity_relationship_extractor import EntityRelationshipExtractor
from app.services.extraction.entity_resolver import EntityResolver
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.normalization_repository import NormalizationRepository
from app.repositories.classification_repository import ClassificationRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NormalizationService(BaseService):
    """Service for normalizing and classifying OCR-extracted insurance documents.
    
    This service uses a hybrid LLM + code approach with chunking and classification:
    1. Chunks pages into manageable segments
    2. Normalizes each chunk using LLM (with signal extraction)
    3. Aggregates classification signals across chunks
    4. Persists chunks, normalized text, and classification to database
    
    The service always uses the hybrid approach with classification enabled.
    
    Attributes:
        llm_normalizer: LLM-based text normalizer with signal extraction
        semantic_normalizer: Semantic field normalizer
        chunking_service: Service for chunking large documents
        classification_service: Service for aggregating classification signals
        fallback_classifier: Fallback classifier for low-confidence cases
        chunk_repository: Repository for chunk CRUD operations
        normalization_repository: Repository for normalization data operations
        classification_repository: Repository for classification data operations
    """

    
    def __init__(
        self,
        openrouter_api_key: Optional[str] = None,
        openrouter_api_url: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        use_hybrid: bool = True,
        chunking_service: Optional[ChunkingService] = None,
        classification_service: Optional[ClassificationService] = None,
        fallback_classifier: Optional[FallbackClassifier] = None,
        chunk_repository: Optional[ChunkRepository] = None,
        normalization_repository: Optional[NormalizationRepository] = None,
        classification_repository: Optional[ClassificationRepository] = None,
        entity_extractor: Optional[EntityRelationshipExtractor] = None,
        entity_resolver: Optional[EntityResolver] = None,
        extractor_factory: Optional[Any] = None,
    ):
        """Initialize OCR normalization service.
        
        Args:
            openrouter_api_key: OpenRouter API key for LLM normalization
            openrouter_api_url: OpenRouter API URL
            openrouter_model: LLM model to use
            use_hybrid: Whether to use hybrid LLM + code approach (default: True)
            chunking_service: Service for chunking large documents
            classification_service: Service for aggregating classification signals
            fallback_classifier: Fallback classifier for low-confidence cases
            chunk_repository: Repository for chunk CRUD operations
            normalization_repository: Repository for normalization data operations
            classification_repository: Repository for classification data operations
            entity_extractor: Entity and relationship extractor
            entity_resolver: Entity resolver for canonical entity mapping
            extractor_factory: Factory for section-specific extractors
        """

        # Initialize BaseService with the primary repository
        super().__init__(repository=normalization_repository)
        
        self.use_hybrid = use_hybrid
        self.semantic_normalizer = SemanticNormalizer()
        self.chunking_service = chunking_service or ChunkingService()
        self.classification_service = classification_service
        self.fallback_classifier = fallback_classifier
        self.chunk_repository = chunk_repository
        self.normalization_repository = normalization_repository
        self.classification_repository = classification_repository
        self.entity_extractor = entity_extractor
        self.entity_resolver = entity_resolver
        self.extractor_factory = extractor_factory
        
        # Initialize LLM normalizer if using hybrid approach
        self.llm_normalizer = None
        if use_hybrid:
            if not openrouter_api_key:
                LOGGER.warning(
                    "Hybrid normalization enabled but no API key provided. "
                    "Falling back to rule-based normalization."
                )
                self.use_hybrid = False
            else:
                self.llm_normalizer = LLMNormalizer(
                    openrouter_api_key=openrouter_api_key,
                    openrouter_api_url=openrouter_api_url,
                    openrouter_model=openrouter_model,
                )
                
                # Initialize entity extractor if not provided
                if not self.entity_extractor:
                    self.entity_extractor = EntityRelationshipExtractor(
                        openrouter_api_key=openrouter_api_key,
                        openrouter_api_url=openrouter_api_url,
                        openrouter_model=openrouter_model,
                    )
        
        LOGGER.info(
            "Initialized OCR normalization service",
            extra={
                "use_hybrid": self.use_hybrid,
                "llm_model": openrouter_model if self.use_hybrid else None,
                "has_classification": classification_service is not None,
                "has_chunk_repo": chunk_repository is not None,
                "has_extractor_factory": extractor_factory is not None,
            }
        )
    

    async def normalize_and_classify_pages(
        self,
        pages: List[PageData],
        document_id: UUID,
        use_chunking: bool = True,
        max_tokens: int = 1500,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Wrapper for run() to maintain backward compatibility.
        
        Delegates to BaseService.execute().
        """
        return await self.execute(
            pages=pages,
            document_id=document_id,
            use_chunking=use_chunking,
            max_tokens=max_tokens
        )

    async def run(
        self,
        pages: List[PageData],
        document_id: UUID,
        use_chunking: bool = True,
        max_tokens: int = 1500,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Normalize pages and perform document classification.
        
        This method combines normalization with classification by:
        1. Chunking pages if needed
        2. Extracting classification signals during normalization
        3. Persisting chunks and signals to database
        4. Aggregating signals for final classification
        5. Using fallback classification if confidence is low
        
        Args:
            pages: List of PageData objects
            document_id: UUID of the document being processed
            use_chunking: Whether to use chunking (default: True)
            max_tokens: Maximum tokens per chunk (default: 1500)
            
        Returns:
            Tuple of (normalized_text, classification_result)
            
        Example:
            >>> service = NormalizationService(...)
            >>> pages = [PageData(...), ...]
            >>> text, classification = await service.normalize_and_classify_pages(pages, doc_id)
            >>> print(classification["classified_type"])  # "policy"
        """
        if not pages:
            LOGGER.warning("Empty pages list provided")
            return "", None
        
        if not self.classification_service or not self.chunk_repository:
            LOGGER.warning("Classification not configured, falling back to normalization only")
            normalized_text = await self.normalize_pages(pages, use_chunking, max_tokens)
            return normalized_text, None
        
        LOGGER.info(
            "Starting normalization with classification",
            extra={
                "document_id": str(document_id),
                "total_pages": len(pages),
                "use_chunking": use_chunking,
            }
        )
        
        # Generate pipeline run ID for provenance tracking
        pipeline_run_id = str(uuid4())
        LOGGER.info(
            "Generated pipeline run ID",
            extra={"pipeline_run_id": pipeline_run_id, "document_id": str(document_id)}
        )
        
        # Chunk pages
        all_chunks = []
        chunk_metadata = []
        
        for page in pages:
            page_text = page.get_content(prefer_markdown=True)
            
            if not page_text or not page_text.strip():
                continue
            
            # Chunk this page
            page_chunks = self.chunking_service.chunk_document(
                text=page_text,
                document_id=document_id
            )
            
            for chunk in page_chunks:
                # Update chunk metadata with page number
                chunk.metadata.page_number = page.page_number
                
                # Generate stable chunk ID
                chunk.metadata.stable_chunk_id = self._generate_stable_chunk_id(
                    document_id=document_id,
                    page_number=page.page_number,
                    chunk_index=chunk.metadata.chunk_index
                )
                
                all_chunks.append(chunk)
                chunk_metadata.append({
                    "page_number": page.page_number,
                    "chunk_index": chunk.metadata.chunk_index,
                })
        
        LOGGER.info(f"Created {len(all_chunks)} chunks from {len(pages)} pages")
        
        # Normalize chunks and extract signals
        normalized_chunks = []
        chunk_signals = []
        all_extracted_fields = []
        
        for i, chunk in enumerate(all_chunks):
            page_num = chunk.metadata.page_number or 1
            
            # Stage 1: LLM normalization with signal extraction AND section detection
            llm_result = await self.llm_normalizer.normalize_with_signals(
                chunk.text,
                page_number=page_num
            )
            
            # Extract section information from LLM result
            section_type = llm_result.get("section_type")
            subsection_type = llm_result.get("subsection_type")
            section_confidence = llm_result.get("section_confidence", 0.0)
            
            # Update chunk metadata with section information
            chunk.metadata.section_type = section_type
            chunk.metadata.subsection_type = subsection_type
            
            # Log section detection
            if section_type:
                LOGGER.info(
                    f"Detected section for chunk {i}",
                    extra={
                        "chunk_index": chunk.metadata.chunk_index,
                        "section_type": section_type,
                        "subsection_type": subsection_type,
                        "confidence": section_confidence,
                    }
                )
            
            # Stage 2: Semantic normalization for field-level accuracy
            semantic_result = self.semantic_normalizer.normalize_text_with_fields(
                llm_result["normalized_text"]
            )
            
            # Use the semantically normalized text as the final output
            final_normalized_text = semantic_result["normalized_text"]
            extracted_fields = semantic_result["extracted_fields"]
            
            normalized_chunks.append(final_normalized_text)
            chunk_signals.append(llm_result)
            all_extracted_fields.append(extracted_fields)
            
            # Persist chunk to database with stable ID and section info
            db_chunk = await self.chunk_repository.create_chunk(
                document_id=document_id,
                page_number=page_num,
                chunk_index=chunk.metadata.chunk_index,
                raw_text=chunk.text,
                token_count=chunk.metadata.token_count,
                section_name=chunk.metadata.section_name,
                stable_chunk_id=chunk.metadata.stable_chunk_id,
                section_type=chunk.metadata.section_type,
                subsection_type=chunk.metadata.subsection_type,
            )
            
            # Compute content hash
            content_hash = hashlib.sha256(final_normalized_text.encode('utf-8')).hexdigest()
            
            # Check if content changed
            content_changed = await self.normalization_repository.check_content_changed(
                chunk_id=db_chunk.id,
                new_content_hash=content_hash
            )
            
            extraction_result = None
            
            if not content_changed:
                LOGGER.info(
                    f"Chunk {chunk.metadata.chunk_index} unchanged (hash: {content_hash[:16]}), skipping entity extraction",
                    extra={"chunk_id": str(db_chunk.id), "content_hash": content_hash[:16]}
                )
                
                # Update existing chunk metadata (pipeline_run_id) without changing content
                await self.normalization_repository.update_normalized_chunk(
                    chunk_id=db_chunk.id,
                    pipeline_run_id=pipeline_run_id,
                )
                
            else:
                LOGGER.info(
                    f"Chunk {chunk.metadata.chunk_index} content changed, proceeding with extraction",
                    extra={"chunk_id": str(db_chunk.id), "content_hash": content_hash[:16]}
                )
                
                # Stage 3: Entity and relationship extraction (if enabled)
                if self.entity_extractor:
                    try:
                        extraction_result = await self.entity_extractor.extract(
                            text=final_normalized_text,
                            chunk_id=db_chunk.id
                        )
                        
                        # Stage 4: Entity resolution (if enabled)
                        if self.entity_resolver and extraction_result.get("entities"):
                            try:
                                await self.entity_resolver.resolve_entities_batch(
                                    entities=extraction_result["entities"],
                                    chunk_id=db_chunk.id,
                                    document_id=document_id
                                )
                                LOGGER.info(
                                    f"Resolved {len(extraction_result['entities'])} entities for chunk {chunk.metadata.chunk_index}",
                                    extra={"chunk_id": str(db_chunk.id)}
                                )
                            except Exception as e:
                                LOGGER.error(
                                    f"Entity resolution failed for chunk {chunk.metadata.chunk_index}: {e}",
                                    exc_info=True
                                )
                    except Exception as e:
                        LOGGER.error(
                            f"Entity extraction failed for chunk {chunk.metadata.chunk_index}: {e}",
                            exc_info=True
                        )
                
                # Section-aware routing using factory pattern
                if chunk.metadata.section_type and content_changed and self.extractor_factory:
                    try:
                        extractor = self.extractor_factory.get_extractor(
                            chunk.metadata.section_type
                        )
                        
                        extracted_items = await extractor.extract(
                            text=final_normalized_text,
                            document_id=document_id,
                            chunk_id=db_chunk.id
                        )
                        
                        LOGGER.info(
                            f"Extracted {len(extracted_items)} items using {extractor.__class__.__name__}",
                            extra={
                                "chunk_id": str(db_chunk.id),
                                "section_type": chunk.metadata.section_type,
                                "extractor": extractor.__class__.__name__,
                                "items_count": len(extracted_items)
                            }
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"Extraction failed for chunk {chunk.metadata.chunk_index}: {e}",
                            exc_info=True,
                            extra={
                                "section_type": chunk.metadata.section_type,
                                "chunk_id": str(db_chunk.id)
                            }
                        )
                
                # Persist normalized chunk (create or update)
                existing_chunk = await self.normalization_repository.get_normalized_chunk_by_id(db_chunk.id)
                
                if existing_chunk:
                    await self.normalization_repository.update_normalized_chunk(
                        chunk_id=db_chunk.id,
                        normalized_text=final_normalized_text,
                        extracted_fields=extracted_fields,
                        entities=extraction_result if extraction_result else None,
                        relationships=extraction_result if extraction_result else None,
                        pipeline_run_id=pipeline_run_id,
                        quality_score=llm_result.get("confidence", 0.8),
                    )
                else:
                    await self.normalization_repository.create_normalized_chunk(
                        chunk_id=db_chunk.id,
                        normalized_text=final_normalized_text,
                        method="hybrid_llm_semantic",
                        extracted_fields=extracted_fields,
                        entities=extraction_result.get("entities") if extraction_result else None,
                        relationships=extraction_result.get("relationships") if extraction_result else None,
                        model_version=self.llm_normalizer.openrouter_model if self.llm_normalizer else None,
                        prompt_version="v1.0",  # TODO: Make this configurable
                        pipeline_run_id=pipeline_run_id,
                        source_stage="normalization",
                        quality_score=llm_result.get("confidence", 0.8),
                    )
            
            # Log extracted fields for monitoring
            if extracted_fields:
                LOGGER.info(
                    f"Extracted fields from chunk {chunk.metadata.chunk_index}",
                    extra={
                        "chunk_id": str(db_chunk.id),
                        "dates_count": len(extracted_fields.get("dates", [])),
                        "amounts_count": len(extracted_fields.get("amounts", [])),
                        "emails_count": len(extracted_fields.get("emails", [])),
                        "extracted_fields": extracted_fields,
                    }
                )
            
            # Persist classification signals using classification repository
            await self.classification_repository.create_classification_signal(
                chunk_id=db_chunk.id,
                signals=llm_result["signals"],
                model_name=self.llm_normalizer.openrouter_model,
                keywords=llm_result.get("keywords", []),
                entities=llm_result.get("entities", {}),
                confidence=llm_result.get("confidence"),
            )
        
        # Log summary of semantic normalization
        total_dates = sum(len(fields.get("dates", [])) for fields in all_extracted_fields)
        total_amounts = sum(len(fields.get("amounts", [])) for fields in all_extracted_fields)
        total_emails = sum(len(fields.get("emails", [])) for fields in all_extracted_fields)
        
        LOGGER.info(
            f"Normalized and persisted {len(normalized_chunks)} chunks with semantic field extraction",
            extra={
                "total_chunks": len(normalized_chunks),
                "total_dates_extracted": total_dates,
                "total_amounts_extracted": total_amounts,
                "total_emails_extracted": total_emails,
            }
        )
        
        # Aggregate signals
        classification_result = self.classification_service.aggregate_signals(
            chunk_signals=chunk_signals,
            chunk_metadata=chunk_metadata,
        )
        
        # Check if fallback is needed
        if self.fallback_classifier and self.classification_service.needs_fallback(classification_result):
            LOGGER.info("Low confidence, triggering fallback classification")
            
            # Collect keywords and top chunks
            all_keywords = classification_result["decision_details"].get("keywords", [])
            top_chunks_text = [nc for nc in normalized_chunks[:5]]  # Top 5 chunks
            
            fallback_result = await self.fallback_classifier.classify(
                keywords=all_keywords,
                top_chunks_text=top_chunks_text,
                aggregated_scores=classification_result["all_scores"],
            )
            
            # Update classification result
            classification_result["classified_type"] = fallback_result["classified_type"]
            classification_result["confidence"] = fallback_result["confidence"]
            classification_result["method"] = "fallback"
            classification_result["fallback_used"] = True
            classification_result["decision_details"]["fallback_reasoning"] = fallback_result.get("reasoning")
        
        # Persist final classification to database
        if self.classification_repository:
            try:
                await self.classification_repository.create_document_classification(
                    document_id=document_id,
                    classified_type=classification_result["classified_type"],
                    confidence=classification_result["confidence"],
                    classifier_model=classification_result.get("method", "aggregate"),
                    decision_details=classification_result.get("decision_details"),
                )
                LOGGER.info("Classification result persisted to database")
            except Exception as e:
                LOGGER.error(f"Failed to persist classification: {e}", exc_info=True)
                # Don't fail the entire operation if classification persistence fails
        
        # Merge normalized chunks
        merged_text = "\n\n".join(normalized_chunks)
        
        LOGGER.info(
            "Normalization and classification completed",
            extra={
                "classified_type": classification_result["classified_type"],
                "confidence": classification_result["confidence"],
                "method": classification_result["method"],
                "chunks_processed": len(normalized_chunks),
            }
        )
        
        return merged_text, classification_result
    

    
    def detect_document_sections(self, text: str) -> Dict[str, List[str]]:
        """Detect common insurance document sections.
        
        This method identifies key sections in insurance documents
        which can be useful for downstream classification and extraction.
        
        Args:
            text: Normalized document text
            
        Returns:
            dict: Dictionary mapping section names to line numbers where found
        """
        sections = {
            "declarations": [],
            "endorsements": [],
            "exclusions": [],
            "insuring_agreement": [],
            "schedule_of_values": [],
            "premium_summary": [],
            "loss_history": [],
            "coverages": [],
        }
        
        section_patterns = {
            "declarations": r'\bdeclarations?\b',
            "endorsements": r'\bendorsements?\b',
            "exclusions": r'\bexclusions?\b',
            "insuring_agreement": r'\binsuring agreement\b',
            "schedule_of_values": r'\bschedule of values\b|\bSOV\b',
            "premium_summary": r'\bpremium summary\b',
            "loss_history": r'\bloss (history|runs?)\b',
            "coverages": r'\bcoverages?\b',
        }
        
        lines = text.split('\n')
        for line_num, line in enumerate(lines, start=1):
            line_lower = line.lower()
            for section_name, pattern in section_patterns.items():
                if re.search(pattern, line_lower):
                    sections[section_name].append(line_num)
        
        detected = {k: v for k, v in sections.items() if v}
        
        if detected:
            LOGGER.info(
                "Detected document sections",
                extra={"sections": list(detected.keys())}
            )
        
        return detected
    
    def _generate_stable_chunk_id(
        self,
        document_id: UUID,
        page_number: int,
        chunk_index: int
    ) -> str:
        """Generate deterministic chunk ID.
        
        Format: doc_{document_id}_p{page_number}_c{chunk_index}
        
        Args:
            document_id: Document UUID
            page_number: Page number (1-indexed)
            chunk_index: Chunk index (0-indexed)
            
        Returns:
            str: Stable chunk ID
        """
        return f"doc_{str(document_id)}_p{page_number}_c{chunk_index}"
    

    

    


