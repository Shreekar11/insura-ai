"""Document service for document management operations."""

from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, SectionExtraction
from app.repositories.document_repository import DocumentRepository
from app.repositories.entity_mention_repository import EntityMentionRepository
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.services.base_service import BaseService
from app.services.storage_service import StorageService
from app.schemas.generated.documents import DocumentResponse, EntityResponse, SectionResponse, DocumentResponse
from app.utils.logging import get_logger
from app.core.exceptions import AppError

LOGGER = get_logger(__name__)


class DocumentService(BaseService):
    """Service for document management operations.
    
    Handles file uploads, document retrieval, and deletion.
    """

    def __init__(self, session: AsyncSession):
        """Initialize document service.
        
        Args:
            session: Database session
        """
        super().__init__()
        self.session = session
        self.doc_repo = DocumentRepository(session)
        self.entity_repo = EntityMentionRepository(session)
        self.chunk_repo = SectionChunkRepository(session)
        self.storage_service = StorageService()

    async def upload_documents(
        self, 
        files: List[UploadFile], 
        user_id: UUID
    ) -> DocumentResponse:
        """Upload and create documents.
        
        Args:
            files: List of uploaded files
            user_id: User ID owning the documents
            
        Returns:
            DocumentResponse with success/failure details
        """
        uploaded_documents: List[DocumentResponse] = []
        failed_uploads: List[dict] = []
        
        for file in files:
            try:
                # Validate file
                if not file.filename:
                    failed_uploads.append({
                        "filename": "unknown",
                        "error": "File has no filename"
                    })
                    continue
                
                # Generate storage path
                import uuid
                file_extension = file.filename.split(".")[-1] if "." in file.filename else "pdf"
                storage_path = f"{user_id}/uploads/{uuid.uuid4()}.{file_extension}"
                
                # Upload to Supabase
                await self.storage_service.upload_file(file, bucket="docs", path=storage_path)
                storage_result = await self.storage_service.get_signed_url(bucket="docs", path=storage_path)
                pdf_url = storage_result["public_url"]
                
                # Create document record
                result = await self.doc_repo.create_document(
                    user_id=user_id,
                    file_path=pdf_url,
                    page_count=0,
                    uploaded_at=datetime.now(),
                )
                
                # Add to successful uploads
                uploaded_documents.append(
                    DocumentResponse(
                        id=result.id,
                        status=result.status,
                        file_path=result.file_path,
                        page_count=result.page_count,
                        uploaded_at=result.uploaded_at
                    )
                )
                
            except Exception as e:
                LOGGER.error(f"Failed to upload document {file.filename}: {e}", exc_info=True)
                failed_uploads.append({
                    "filename": file.filename,
                    "error": str(e)
                })
                continue
        
        return DocumentResponse(
            documents=uploaded_documents,
            total_uploaded=len(uploaded_documents),
            failed_uploads=failed_uploads
        )

    async def list_documents(
        self, 
        user_id: UUID, 
        limit: int = 50, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """List documents for a user.
        
        Args:
            user_id: User ID
            limit: Pagination limit
            offset: Pagination offset
            
        Returns:
            Dict with total count and list of documents
        """
        filters = {"user_id": user_id}
        documents = await self.doc_repo.get_all(skip=offset, limit=limit, filters=filters)
        total = await self.doc_repo.count(filters=filters)
        
        return {
            "total": total,
            "documents": [
                DocumentResponse(
                    id=doc.id,
                    status=doc.status,
                    file_path=doc.file_path,
                    page_count=doc.page_count,
                    uploaded_at=doc.uploaded_at
                ) for doc in documents
            ]
        }

    async def get_document(self, document_id: UUID, user_id: UUID) -> Optional[DocumentResponse]:
        """Get a specific document.
        
        Args:
            document_id: Document ID
            user_id: User ID (for ownership check)
            
        Returns:
            DocumentResponse or None if not found/no access
        """
        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.user_id != user_id:
            return None
            
        return DocumentResponse(
            id=document.id,
            status=document.status,
            file_path=document.file_path,
            page_count=document.page_count,
            uploaded_at=document.uploaded_at
        )

    async def delete_document(self, document_id: UUID, user_id: UUID) -> bool:
        """Delete a document.
        
        Args:
            document_id: Document ID
            user_id: User ID
            
        Returns:
            True if deleted, False if not found/no access
        """
        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.user_id != user_id:
            return False
        
        await self.doc_repo.delete(document_id)
        await self.session.commit()
        return True

    async def get_document_entities(
        self, 
        document_id: UUID, 
        user_id: UUID, 
        entity_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get entities for a document.
        
        Args:
            document_id: Document ID
            user_id: User ID
            entity_type: Optional filter
            
        Returns:
            Dict with entities or None if doc not found
        """
        # Verify ownership
        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.user_id != user_id:
            return None
            
        entities = await self.entity_repo.get_by_document_id(document_id, entity_type=entity_type)
        
        return {
            "total": len(entities),
            "entities": [
                EntityResponse(
                    id=e.id,
                    type=e.entity_type,
                    value=e.mention_text,
                    confidence=float(e.confidence) if e.confidence else None,
                    extracted_fields=e.extracted_fields
                ) for e in entities
            ]
        }

    async def get_document_sections(self, document_id: UUID, user_id: UUID) -> Optional[Dict[str, Any]]:
        """Get sections for a document.
        
        Args:
            document_id: Document ID
            user_id: User ID
            
        Returns:
            Dict with sections or None if doc not found
        """
        # Verify ownership
        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.user_id != user_id:
            return None
            
        summary = await self.chunk_repo.get_section_summary(document_id)
        
        sections = []
        for section_type, data in summary.get("sections", {}).items():
            sections.append(SectionResponse(
                section_type=section_type,
                chunk_count=data["chunk_count"],
                page_range=data["page_range"]
            ))
            
        return {"sections": sections}
