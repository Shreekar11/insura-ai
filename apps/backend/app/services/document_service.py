"""Document service for document management operations."""

from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, SectionExtraction
from app.repositories.document_repository import DocumentRepository
from app.repositories.workflow_repository import WorkflowDocumentRepository
from app.repositories.entity_mention_repository import EntityMentionRepository
from app.repositories.section_chunk_repository import SectionChunkRepository
from app.services.base_service import BaseService
from app.services.storage_service import StorageService
from app.schemas.generated.documents import DocumentResponse, EntityResponse, SectionResponse, MultipleDocumentResponse
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
        self.wf_doc_repo = WorkflowDocumentRepository(session)

    async def run(self, *args, **kwargs) -> Any:
        """Route to appropriate handler based on action.
        
        This implements the abstract run() method from BaseService.
        """
        action = kwargs.get("action")
        
        if action == "upload_documents":
            return await self._upload_documents_logic(
                kwargs.get("files"),
                kwargs.get("user_id"),
                kwargs.get("workflow_id")
            )
        elif action == "list_documents":
            return await self._list_documents_logic(
                kwargs.get("user_id"),
                kwargs.get("limit", 50),
                kwargs.get("offset", 0),
                kwargs.get("workflow_id")
            )
        else:
            raise AppError(f"Unknown action: {action}")

    async def upload_documents(
        self, 
        files: List[UploadFile], 
        user_id: UUID,
        workflow_id: UUID
    ) -> MultipleDocumentResponse:
        """Upload and create documents.
        
        Args:
            files: List of uploaded files
            user_id: User ID owning the documents
            
        Returns:
            MultipleDocumentResponse with success/failure details
        """
        return await self.execute(
            action="upload_documents",
            files=files,
            user_id=user_id,
            workflow_id=workflow_id
        )

    async def _upload_documents_logic(
        self, 
        files: List[UploadFile], 
        user_id: UUID,
        workflow_id: UUID
    ) -> MultipleDocumentResponse:
        """Core logic for uploading and creating documents."""
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
                
                # Upload to Supabase Storage
                await self.storage_service.upload_file(file, bucket="docs", path=storage_path)
                
                # Store the storage path, not the public URL
                # URLs will be generated on-demand with proper signing
                pdf_storage_path = storage_path
                
                LOGGER.info(
                    f"File uploaded to storage: "
                    f"filename={file.filename}, "
                    f"path={storage_path}"
                )
                
                # Create document record
                document = await self.doc_repo.create_document(
                    user_id=user_id,
                    file_path=pdf_storage_path,  # Store path, generate signed URL on access
                    document_name=file.filename,
                    page_count=0,
                )
                
                if not document or not document.id:
                    raise ValueError(f"Document creation failed for {file.filename}")
                
                LOGGER.info(
                    f"Document created: "
                    f"document_id={document.id}, "
                    f"filename={file.filename}, "
                    f"status={document.status}"
                )
                
                # Create workflow-document association
                workflow_doc = await self.wf_doc_repo.create_workflow_document(
                    document_id=document.id,
                    workflow_id=workflow_id,
                )
                
                if not workflow_doc:
                    raise ValueError(
                        f"Workflow document association failed: "
                        f"document_id={document.id}, workflow_id={workflow_id}"
                    )
                
                LOGGER.info(
                    f"Workflow association created: "
                    f"document_id={document.id}, "
                    f"workflow_id={workflow_id}"
                )
                
                # Commit transaction
                await self.session.commit()
                
                LOGGER.info(
                    f"Document upload completed: "
                    f"filename={file.filename}, "
                    f"document_id={document.id}"
                )
                
                # Add to successful uploads
                uploaded_documents.append(
                    DocumentResponse(
                        id=document.id,
                        status=document.status,
                        file_path=document.file_path,
                        document_name=document.document_name,
                        page_count=document.page_count,
                        created_at=document.uploaded_at
                    )
                )
                
            except Exception as e:
                # Rollback on error
                await self.session.rollback()
                
                LOGGER.error(
                    f"Document upload failed: "
                    f"filename={file.filename}, "
                    f"error={str(e)}",
                    exc_info=True,
                    extra={
                        "filename": file.filename,
                        "user_id": str(user_id),
                        "workflow_id": str(workflow_id),
                        "error_type": type(e).__name__
                    }
                )
                
                failed_uploads.append({
                    "filename": file.filename,
                    "error": str(e)
                })
                continue
        
        # Log batch summary
        LOGGER.info(
            f"Upload batch completed: "
            f"total={len(files)}, "
            f"successful={len(uploaded_documents)}, "
            f"failed={len(failed_uploads)}, "
            f"workflow_id={workflow_id}"
        )
        
        return MultipleDocumentResponse(
            documents=uploaded_documents,
            total_uploaded=len(uploaded_documents),
            failed_uploads=failed_uploads
        )

    async def list_documents(
        self, 
        user_id: UUID, 
        limit: int = 50, 
        offset: int = 0,
        workflow_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """List documents for a user.
        
        Args:
            user_id: User ID
            limit: Pagination limit
            offset: Pagination offset
            workflow_id: Optional workflow filter
            
        Returns:
            Dict with total count and list of documents
        """
        return await self.execute(
            action="list_documents",
            user_id=user_id,
            limit=limit,
            offset=offset,
            workflow_id=workflow_id
        )

    async def _list_documents_logic(
        self, 
        user_id: UUID, 
        limit: int = 50, 
        offset: int = 0,
        workflow_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        if workflow_id:
            documents = await self.wf_doc_repo.get_documents_for_workflow(workflow_id)
            # Filter by user_id to ensure ownership
            documents = [d for d in documents if d.user_id == user_id]
            total = len(documents)
            # Apply pagination in memory for workflow docs
            documents = documents[offset:offset+limit]
        else:
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
                    document_name=doc.document_name,
                    page_count=doc.page_count,
                    created_at=doc.uploaded_at
                ) for doc in documents
            ]
        }

    async def get_document(self, document_id: UUID, user_id: UUID) -> Optional[DocumentResponse]:
        """Get a specific document."""
        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.user_id != user_id:
            return None
            
        return DocumentResponse(
            id=document.id,
            status=document.status,
            file_path=document.file_path,
            document_name=document.document_name,
            page_count=document.page_count,
            created_at=document.uploaded_at
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

    async def get_document_url(self, document_id: UUID, user_id: UUID) -> Optional[str]:
        """Get a secure signed URL for document access.
        
        Args:
            document_id: Document ID
            user_id: User ID (for ownership verification)
            
        Returns:
            Signed URL valid for 24 hours, or None if not found/unauthorized
        """
        document = await self.doc_repo.get_by_id(document_id)
        if not document or document.user_id != user_id:
            return None
        
        return await self.storage_service.create_download_url(
            bucket="docs",
            path=document.file_path,
            expires_in=86400  # 24 hours
        )

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
