"""Pipeline debugging utilities."""

from typing import Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.repositories.page_analysis_repository import PageAnalysisRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.normalization_repository import NormalizationRepository
from app.repositories.classification_repository import ClassificationRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


async def get_pipeline_status(session: AsyncSession, document_id: UUID) -> Dict[str, Any]:
    """Get complete pipeline status for a document."""
    doc_repo = DocumentRepository(session)
    page_repo = PageAnalysisRepository(session)
    chunk_repo = ChunkRepository(session)
    norm_repo = NormalizationRepository(session)
    class_repo = ClassificationRepository(session)

    document = await doc_repo.get_by_id(document_id)
    if not document:
        return {"error": "Document not found"}

    manifest = await page_repo.get_manifest(document_id)
    pages = await doc_repo.get_pages_by_document(document_id)
    chunks = await chunk_repo.get_by_document(document_id)
    normalized = await norm_repo.get_by_document(document_id)
    classification = await class_repo.get_by_document(document_id)

    return {
        "document": {
            "id": str(document.id),
            "status": document.status,
            "file_path": document.file_path,
            "created_at": document.created_at.isoformat() if document.created_at else None,
        },
        "page_analysis": {
            "total_pages": manifest.total_pages if manifest else 0,
            "pages_to_process": len(manifest.pages_to_process) if manifest else 0,
            "manifest_exists": manifest is not None,
        },
        "ocr_status": {
            "pages_extracted": len(pages),
            "status": "complete" if pages else "pending",
        },
        "normalization_status": {
            "chunk_count": len(chunks),
            "normalized_count": len(normalized),
            "is_classified": classification is not None,
        },
    }

