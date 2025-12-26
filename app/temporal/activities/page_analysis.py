"""Page analysis activities for Temporal workflows.

These activities extract page signals, classify pages, and create manifests
to determine which pages should undergo full OCR processing.

PageAnalysisPipeline uses singleton instances for stateless components
(PageAnalyzer, PageClassifier) to optimize initialization overhead.
These singletons are safe for use in Temporal activities because they are stateless
and only contain immutable configuration. Activities run in worker processes, not
workflow code.
"""

from temporalio import activity
from typing import List, Dict
from uuid import UUID

from app.database.base import async_session_maker
from app.pipeline.page_analysis import PageAnalysisPipeline
from app.models.page_analysis_models import PageSignals, PageClassification
from app.utils.logging import get_logger

logger = get_logger(__name__)


@activity.defn
async def extract_page_signals(document_id: str) -> List[Dict]:
    """Extract lightweight signals from all pages using Docling's selective extraction.
    
    This is the first activity in the page analysis workflow. It extracts lightweight
    signals from PDF pages without performing full OCR, enabling cost-effective page
    classification.
    
    Args:
        document_id: UUID string of the document to analyze
        
    Returns:
        List of page signal dictionaries, one per page
        
    Context Transfer:
        - Input: document_id (from workflow)
        - Output: page_signals (to classify_pages activity)
    """
    activity.logger.info(
        "[Phase 0: Page Analysis] Starting page signal extraction",
        extra={
            "document_id": document_id,
            "activity": "extract_page_signals",
            "workflow_stage": "page_analysis"
        }
    )
    
    try:
        async with async_session_maker() as session:
            # Get document to retrieve file_path
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            
            activity.logger.debug(
                "Fetching document metadata",
                extra={"document_id": document_id}
            )
            
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document:
                raise ValueError(f"Document {document_id} not found")
            
            if not document.file_path:
                raise ValueError(f"Document {document_id} has no file path")
            
            activity.logger.info(
                "Document metadata retrieved",
                extra={
                    "document_id": document_id,
                    "file_path": document.file_path,
                    "page_count": document.page_count
                }
            )
            
            # Initialize pipeline
            activity.logger.debug("Initializing PageAnalysisPipeline")
            pipeline = PageAnalysisPipeline(session)
            
            # Extract signals from all pages
            activity.logger.info(
                "Extracting page signals using Docling selective extraction",
                extra={"document_id": document_id}
            )
            
            signals = await pipeline.extract_signals(UUID(document_id), document.file_path)
            
            activity.logger.info(
                "Page signals extracted, persisting to database",
                extra={
                    "document_id": document_id,
                    "signals_count": len(signals)
                }
            )
            
            await session.commit()
            
            # Serialize for context transfer to next activity
            serialized_signals = [s.dict() for s in signals]
            
            # Log signal summary for context transfer
            signal_summary = {
                "total_pages": len(serialized_signals),
                "pages_with_text": sum(1 for s in serialized_signals if s.get("has_text", False)),
                "pages_with_tables": sum(1 for s in serialized_signals if s.get("has_tables", False)),
                "avg_text_density": sum(s.get("text_density", 0) for s in serialized_signals) / len(serialized_signals) if serialized_signals else 0,
            }
            
            activity.logger.info(
                "[Phase 0: Page Analysis] Page signal extraction completed successfully",
                extra={
                    "document_id": document_id,
                    "total_pages": len(serialized_signals),
                    "signal_summary": signal_summary,
                    "context_transfer": {
                        "output_type": "page_signals",
                        "output_count": len(serialized_signals),
                        "next_activity": "classify_pages"
                    }
                }
            )
            
            return serialized_signals
            
    except Exception as e:
        activity.logger.error(
            "Page signal extraction activity failed",
            extra={
                "document_id": document_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        raise


@activity.defn
async def classify_pages(document_id: str, page_signals: List[Dict]) -> List[Dict]:
    """Classify pages using rule-based classifier with duplicate detection.
    
    This activity receives page signals from extract_page_signals and applies
    insurance-specific classification rules and duplicate detection.
    
    Args:
        document_id: UUID string of the document
        page_signals: List of page signal dictionaries from extract_page_signals
        
    Returns:
        List of page classification dictionaries
        
    Context Transfer:
        - Input: page_signals (from extract_page_signals activity)
        - Output: classifications (to create_page_manifest activity)
    """
    activity.logger.info(
        "[Phase 0: Page Analysis] Starting page classification",
        extra={
            "document_id": document_id,
            "activity": "classify_pages",
            "workflow_stage": "page_analysis",
            "input_context": {
                "source_activity": "extract_page_signals",
                "page_signals_count": len(page_signals)
            }
        }
    )
    
    try:
        # Validate input context
        if not page_signals:
            raise ValueError("No page signals received from extract_page_signals activity")
        
        activity.logger.debug(
            "Validating page signals input",
            extra={
                "document_id": document_id,
                "signals_count": len(page_signals),
                "sample_signal_keys": list(page_signals[0].keys()) if page_signals else []
            }
        )
        
        async with async_session_maker() as session:
            pipeline = PageAnalysisPipeline(session)
            
            # Deserialize signals from previous activity
            activity.logger.debug(
                "Deserializing page signals",
                extra={"document_id": document_id, "signals_count": len(page_signals)}
            )
            
            signals_objs = [PageSignals(**s) for s in page_signals]
            
            # Classify pages (includes duplicate detection)
            activity.logger.info(
                "Classifying pages using rule-based classifier",
                extra={
                    "document_id": document_id,
                    "pages_to_classify": len(signals_objs)
                }
            )
            
            classifications = await pipeline.classify_pages(UUID(document_id), signals_objs)
            
            activity.logger.info(
                "Page classifications completed, persisting to database",
                extra={
                    "document_id": document_id,
                    "classifications_count": len(classifications)
                }
            )
            
            await session.commit()
            
            # Calculate classification statistics
            pages_to_process = sum(1 for c in classifications if c.should_process)
            pages_skipped = sum(1 for c in classifications if not c.should_process)
            duplicates = sum(1 for c in classifications if c.page_type.value == "duplicate")
            
            # Count by page type
            type_counts = {}
            for c in classifications:
                page_type = c.page_type.value
                type_counts[page_type] = type_counts.get(page_type, 0) + 1
            
            activity.logger.info(
                "[Phase 0: Page Analysis] Page classification completed successfully",
                extra={
                    "document_id": document_id,
                    "total_pages": len(classifications),
                    "pages_to_process": pages_to_process,
                    "pages_skipped": pages_skipped,
                    "duplicates_detected": duplicates,
                    "type_distribution": type_counts,
                    "processing_ratio": pages_to_process / len(classifications) if classifications else 0.0,
                    "context_transfer": {
                        "output_type": "classifications",
                        "output_count": len(classifications),
                        "next_activity": "create_page_manifest"
                    }
                }
            )
            
            # Serialize for context transfer to next activity
            return [c.dict() for c in classifications]
            
    except Exception as e:
        activity.logger.error(
            "Page classification failed",
            extra={
                "document_id": document_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "input_signals_count": len(page_signals) if page_signals else 0
            },
            exc_info=True
        )
        raise


@activity.defn
async def create_page_manifest(document_id: str, classifications: List[Dict]) -> Dict:
    """Create and persist page manifest with document profile to database.
    
    This is the final activity in the page analysis workflow. It creates a manifest
    that determines which pages should undergo full OCR processing, and includes
    a document profile.
    
    Args:
        document_id: UUID string of the document
        classifications: List of page classification dictionaries from classify_pages
        
    Returns:
        Dictionary containing manifest data with:
        - Computed properties (processing_ratio, cost_savings_estimate)
        - Document profile (document_type, section_boundaries, page_section_map)
        
    Context Transfer:
        - Input: classifications (from classify_pages activity)
        - Output: manifest with document_profile (used by OCR, chunking, and extraction)
    """
    activity.logger.info(
        "[Phase 0: Page Analysis] Creating page manifest with document profile",
        extra={
            "document_id": document_id,
            "activity": "create_page_manifest",
            "workflow_stage": "page_analysis",
            "input_context": {
                "source_activity": "classify_pages",
                "classifications_count": len(classifications)
            }
        }
    )
    
    try:
        # Validate input context
        if not classifications:
            raise ValueError("No classifications received from classify_pages activity")
        
        activity.logger.debug(
            "Validating classifications input",
            extra={
                "document_id": document_id,
                "classifications_count": len(classifications),
                "sample_classification_keys": list(classifications[0].keys()) if classifications else []
            }
        )
        
        async with async_session_maker() as session:
            pipeline = PageAnalysisPipeline(session)
            
            # Deserialize classifications from previous activity
            activity.logger.debug(
                "Deserializing page classifications",
                extra={"document_id": document_id, "classifications_count": len(classifications)}
            )
            
            class_objs = [PageClassification(**c) for c in classifications]
            
            # Build document profile (replaces Tier 1 LLM classification)
            activity.logger.info(
                "Building document profile from page classifications",
                extra={
                    "document_id": document_id,
                    "total_classifications": len(class_objs)
                }
            )
            
            document_profile = await pipeline.build_document_profile(
                UUID(document_id), 
                class_objs
            )
            
            activity.logger.info(
                "Document profile built successfully",
                extra={
                    "document_id": document_id,
                    "document_type": document_profile.document_type.value,
                    "confidence": document_profile.confidence,
                    "section_count": len(document_profile.section_boundaries),
                }
            )
            
            # Create manifest with document profile
            manifest = await pipeline.create_manifest(
                UUID(document_id), 
                class_objs,
                document_profile=document_profile
            )
            
            activity.logger.info(
                "Page manifest created with document profile, persisting to database",
                extra={
                    "document_id": document_id,
                    "total_pages": manifest.total_pages,
                    "pages_to_process": len(manifest.pages_to_process),
                    "pages_skipped": len(manifest.pages_skipped),
                    "document_type": document_profile.document_type.value,
                }
            )
            
            await session.commit()
            
            # Serialize manifest and include computed properties
            manifest_dict = manifest.model_dump()
            manifest_dict['processing_ratio'] = manifest.processing_ratio
            manifest_dict['cost_savings_estimate'] = manifest.cost_savings_estimate
            
            # Ensure document_profile is properly serialized
            if manifest.document_profile:
                manifest_dict['document_profile'] = manifest.document_profile.model_dump()
                # Convert UUID to string for JSON serialization
                manifest_dict['document_profile']['document_id'] = str(
                    manifest.document_profile.document_id
                )
                # Convert section boundaries to dicts
                manifest_dict['document_profile']['section_boundaries'] = [
                    {
                        'section_type': sb.section_type.value,
                        'start_page': sb.start_page,
                        'end_page': sb.end_page,
                        'confidence': sb.confidence,
                        'page_count': sb.page_count,
                        'anchor_text': sb.anchor_text,
                    }
                    for sb in manifest.document_profile.section_boundaries
                ]
                # Convert document_type enum to string
                manifest_dict['document_profile']['document_type'] = (
                    manifest.document_profile.document_type.value
                )
            
            # Convert document_id to string for JSON serialization
            manifest_dict['document_id'] = str(manifest.document_id)
            
            # Convert classifications page_type enums to strings
            manifest_dict['classifications'] = [
                {
                    **c,
                    'page_type': c['page_type'].value if hasattr(c['page_type'], 'value') else c['page_type']
                }
                for c in manifest_dict['classifications']
            ]
            
            # Log final manifest summary with document profile
            activity.logger.info(
                "[Phase 0: Page Analysis] Page manifest with document profile created successfully",
                extra={
                    "document_id": document_id,
                    "manifest_summary": {
                        "total_pages": manifest.total_pages,
                        "pages_to_process": len(manifest.pages_to_process),
                        "pages_skipped": len(manifest.pages_skipped),
                        "processing_ratio": manifest.processing_ratio,
                        "cost_savings_estimate": manifest.cost_savings_estimate,
                    },
                    "document_profile_summary": {
                        "document_type": document_profile.document_type.value,
                        "document_subtype": document_profile.document_subtype,
                        "confidence": document_profile.confidence,
                        "section_count": len(document_profile.section_boundaries),
                        "sections": [
                            sb.section_type.value 
                            for sb in document_profile.section_boundaries
                        ],
                    },
                    "workflow_completion": {
                        "status": "success",
                        "output_type": "manifest_with_profile",
                        "downstream_workflows": ["ocr_extraction", "hybrid_chunking", "tiered_extraction"],
                        "tier1_llm_replaced": True,
                    }
                }
            )
            
            return manifest_dict
            
    except Exception as e:
        activity.logger.error(
            "Failed to create page manifest",
            extra={
                "document_id": document_id,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "input_classifications_count": len(classifications) if classifications else 0
            },
            exc_info=True
        )
        raise
