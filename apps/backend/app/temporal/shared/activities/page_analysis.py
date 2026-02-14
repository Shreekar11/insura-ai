"""Page analysis activities for Temporal workflows."""

from temporalio import activity
from typing import List, Dict, Tuple, Optional, Any
from uuid import UUID

from app.core.database import async_session_maker
from app.pipeline.page_analysis import PageAnalysisPipeline
from app.models.page_analysis_models import PageSignals, PageClassification
from app.utils.logging import get_logger
from app.temporal.core.activity_registry import ActivityRegistry

logger = get_logger(__name__)


@ActivityRegistry.register("shared", "extract_page_signals")
@activity.defn
async def extract_page_signals(document_id: str) -> List[Dict]:
    """Extract lightweight signals from all pages using Docling's selective extraction."""
    activity.logger.info(
        "[Phase 0: Page Analysis] Starting page signal extraction",
        extra={"document_id": document_id}
    )
    
    try:
        async with async_session_maker() as session:
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            document = await doc_repo.get_by_id(UUID(document_id))
            
            if not document or not document.file_path:
                raise ValueError(f"Document {document_id} not found or has no file path")
            
            pipeline = PageAnalysisPipeline(session)
            
            # Check if pages are already extracted
            existing_pages = await doc_repo.get_pages(UUID(document_id))
            
            if existing_pages:
                markdown_pages = [(p.markdown, p.page_number, p.metadata) for p in existing_pages]
                signals, doc_type, confidence = await pipeline.extract_signals_from_markdown(
                    document_id=UUID(document_id), 
                    pages=markdown_pages
                )
            else:
                from app.services.storage_service import StorageService
                storage_service = StorageService()
                signed_url = await storage_service.create_download_url(
                    bucket="docs",
                    path=document.file_path,
                    expires_in=3600 # 1 hour
                )
                signals = await pipeline.extract_signals(
                    document_id=UUID(document_id), 
                    document_url=signed_url
                )
            
            await session.commit()
            return [s.dict() for s in signals]
            
    except Exception as e:
        activity.logger.error(f"Page signal extraction failed: {e}", exc_info=True)
        raise


@ActivityRegistry.register("shared", "extract_page_signals_from_markdown")
@activity.defn
async def extract_page_signals_from_markdown(
    document_id: str, 
    markdown_pages: List[Tuple[str, int, Optional[Dict[str, Any]]]]
) -> List[Dict]:
    """Extract page signals from provided markdown pages using Docling output."""
    try:
        async with async_session_maker() as session:
            pipeline = PageAnalysisPipeline(session)
            signals, doc_type, confidence = await pipeline.extract_signals_from_markdown(
                document_id=UUID(document_id), 
                pages=markdown_pages
            )
            await session.commit()
            return [s.dict() for s in signals]
    except Exception as e:
        activity.logger.error(f"Failed to extract signals from markdown: {e}", exc_info=True)
        raise


@ActivityRegistry.register("shared", "classify_pages")
@activity.defn
async def classify_pages(document_id: str, page_signals: List[Dict]) -> List[Dict]:
    """Classify pages using rule-based classifier with duplicate detection."""
    try:
        async with async_session_maker() as session:
            pipeline = PageAnalysisPipeline(session)
            signals_objs = [PageSignals(**s) for s in page_signals]
            classifications = await pipeline.classify_pages(document_id=UUID(document_id), page_signals=signals_objs)
            await session.commit()
            return [c.model_dump(mode='json') for c in classifications]
    except Exception as e:
        activity.logger.error(f"Page classification failed: {e}", exc_info=True)
        raise


@ActivityRegistry.register("shared", "create_page_manifest")
@activity.defn
async def create_page_manifest(
    document_id: str, 
    classifications: List[Dict],
    workflow_name: Optional[str] = None
) -> Dict:
    """Create and persist page manifest with document profile to database."""
    try:
        async with async_session_maker() as session:
            pipeline = PageAnalysisPipeline(session)
            class_objs = [PageClassification(**c) for c in classifications]
            
            document_profile = await pipeline.build_document_profile(
                document_id=UUID(document_id), 
                classifications=class_objs,
                workflow_name=workflow_name,
            )
            
            manifest = await pipeline.create_manifest(
                document_id=UUID(document_id),
                classifications=class_objs,
                document_profile=document_profile,
                workflow_name=workflow_name,
            )
            
            from app.repositories.document_repository import DocumentRepository
            doc_repo = DocumentRepository(session)
            await doc_repo.update_page_metadata_bulk(
                UUID(document_id), 
                document_profile.page_section_map
            )
            
            await session.commit()
            
            manifest_dict = manifest.model_dump()
            manifest_dict['processing_ratio'] = manifest.processing_ratio
            manifest_dict['cost_savings_estimate'] = manifest.cost_savings_estimate
            
            if manifest.document_profile:
                manifest_dict['document_profile'] = manifest.document_profile.model_dump()
                manifest_dict['document_profile']['document_id'] = str(manifest.document_profile.document_id)
                manifest_dict['document_profile']['section_boundaries'] = [
                    {
                        'section_type': sb.section_type.value,
                        'start_page': sb.start_page,
                        'end_page': sb.end_page,
                        'start_line': sb.start_line,
                        'end_line': sb.end_line,
                        'confidence': sb.confidence,
                        'page_count': sb.page_count,
                        'anchor_text': sb.anchor_text,
                        'semantic_role': sb.semantic_role.value if sb.semantic_role else None,
                        'effective_section_type': sb.effective_section_type.value if sb.effective_section_type else None,
                        'coverage_effects': [e.value for e in sb.coverage_effects],
                        'exclusion_effects': [e.value for e in sb.exclusion_effects],
                    }
                    for sb in manifest.document_profile.section_boundaries
                ]
                manifest_dict['document_profile']['document_type'] = manifest.document_profile.document_type.value
            
            manifest_dict['document_id'] = str(manifest.document_id)
            manifest_dict['classifications'] = [
                {
                    **c,
                    'page_type': c['page_type'].value if hasattr(c['page_type'], 'value') else c['page_type'],
                    'semantic_role': c['semantic_role'].value if c.get('semantic_role') and hasattr(c['semantic_role'], 'value') else c.get('semantic_role'),
                    'coverage_effects': [e.value for e in c['coverage_effects']] if c.get('coverage_effects') else [],
                    'exclusion_effects': [e.value for e in c['exclusion_effects']] if c.get('exclusion_effects') else [],
                }
                for c in manifest_dict['classifications']
            ]
            
            return manifest_dict
    except Exception as e:
        activity.logger.error(f"Failed to create page manifest: {e}", exc_info=True)
        raise


@ActivityRegistry.register("shared", "get_document_profile_activity")
@activity.defn
async def get_document_profile_activity(document_id: str) -> Dict:
    """Retrieve document profile from database."""
    try:
        async with async_session_maker() as session:
            from app.repositories.page_analysis_repository import PageAnalysisRepository
            from app.pipeline.page_analysis import PageAnalysisPipeline
            
            repo = PageAnalysisRepository(session)
            pipeline = PageAnalysisPipeline(session)
            
            classifications = await repo.get_classifications(UUID(document_id))
            if not classifications:
                raise ValueError(f"No classifications found for document {document_id}")
            
            document_profile = await pipeline.build_document_profile(
                document_id=UUID(document_id),
                classifications=classifications
            )
            
            profile_dict = document_profile.model_dump()
            profile_dict['document_id'] = str(profile_dict['document_id'])
            profile_dict['document_type'] = profile_dict['document_type'].value
            profile_dict['section_boundaries'] = [
                {
                    'section_type': sb.section_type.value,
                    'start_page': sb.start_page,
                    'end_page': sb.end_page,
                    'start_line': sb.start_line,
                    'end_line': sb.end_line,
                    'confidence': sb.confidence,
                    'page_count': sb.page_count,
                    'anchor_text': sb.anchor_text,
                    'semantic_role': sb.semantic_role.value if sb.semantic_role else None,
                    'effective_section_type': sb.effective_section_type.value if sb.effective_section_type else None,
                    'coverage_effects': [e.value for e in sb.coverage_effects],
                    'exclusion_effects': [e.value for e in sb.exclusion_effects],
                }
                for sb in document_profile.section_boundaries
            ]
            
            return profile_dict
    except Exception as e:
        activity.logger.error(f"Failed to retrieve document profile: {e}", exc_info=True)
        raise
