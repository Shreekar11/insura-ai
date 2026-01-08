import hashlib
import json
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sentence_transformers import SentenceTransformer

from app.services.base_service import BaseService
from app.services.summarized.contracts import EmbeddingResult
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.workflow_repository import WorkflowDocumentRepository
from app.services.summarized.services.vector_template_service import VectorTemplateService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class GenerateEmbeddingsService(BaseService):
    """Service for generating vector embeddings for document sections.
    
    This service implements the high-accuracy vector indexing strategy:
    1. Retrieves extracted sections for a document.
    2. Uses templates to create deterministic semantic text for each business unit.
    3. Generates 384-dimensional embeddings using 'all-MiniLM-L6-v2'.
    4. Persists embeddings in pgvector for semantic recall.
    """

    def __init__(self, session):
        """Initialize the embedding service with required repositories and model."""
        super().__init__(VectorEmbeddingRepository(session))
        self.session = session
        self.vector_repo = self.repository
        self.section_repo = SectionExtractionRepository(session)
        self.workflow_doc_repo = WorkflowDocumentRepository(session)
        self.template_service = VectorTemplateService()
        self.model_name = "all-MiniLM-L6-v2"
        self._model = None  # Lazy load the model

    @property
    def model(self) -> SentenceTransformer:
        """Lazy loader for the SentenceTransformer model."""
        if self._model is None:
            LOGGER.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    async def run(self, document_id: UUID, workflow_id: Optional[UUID] = None) -> EmbeddingResult:
        """Generate and store embeddings for all sections of a document.
        
        Args:
            document_id: UUID of the document to process
            workflow_id: Optional UUID of the workflow
            
        Returns:
            EmbeddingResult with processing statistics
        """
        # 0. Clean up existing embeddings for this document to avoid duplicates
        await self.vector_repo.delete_by_document(document_id)

        # 1. Fetch the workflow document to get a valid workflow_id if not provided
        if not workflow_id:
            msg = f"No workflow_id provided for document {document_id}, trying to find recent one"
            workflow_docs = await self.workflow_doc_repo.get_by_workflow_and_document_id(workflow_id, document_id)
            if isinstance(workflow_docs, list) and workflow_docs:
                workflow_id = workflow_docs[0].workflow_id
            elif workflow_docs:
                workflow_id = workflow_docs.workflow_id
            
            if workflow_id:
                LOGGER.info(f"{msg}: found {workflow_id}")

        # 2. Fetch all section extractions for this document
        if not workflow_id:
            LOGGER.warning(f"No workflow_id found for document {document_id}, fetching all sections")
            from sqlalchemy import select
            from app.database.models import SectionExtraction
            stmt = select(SectionExtraction).where(SectionExtraction.document_id == document_id)
            result = await self.session.execute(stmt)
            sections = list(result.scalars().all())
        else:
            sections = await self.section_repo.get_by_document(document_id, workflow_id)

        if not sections:
            LOGGER.info(f"No sections found for document {document_id}")
            return EmbeddingResult(vector_dimension=384, chunks_embedded=0, storage_details={"status": "no_sections"})

        # 3. Process each section and generate embeddings
        embeddings_created = 0
        
        for section in sections:
            section_type = section.section_type
            data = section.extracted_fields
            
            # Certain sections contain lists of entities that should be embedded individually
            if section_type.lower() == "coverages" and "coverages" in data:
                for idx, entry in enumerate(data.get("coverages", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"cov_{idx}", "coverage", workflow_id
                    )
            elif section_type.lower() == "loss_run" and "claims" in data:
                for idx, entry in enumerate(data.get("claims", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"claim_{idx}", "claim", workflow_id
                    )
            elif section_type.lower() == "schedule_of_values" and "locations" in data:
                for idx, entry in enumerate(data.get("locations", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"loc_{idx}", "location", workflow_id
                    )
            elif section_type.lower() == "endorsements" and "endorsements" in data:
                for idx, entry in enumerate(data.get("endorsements", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"end_{idx}", "endorsement", workflow_id
                    )
            elif section_type.lower() == "exclusions" and "exclusions" in data:
                for idx, entry in enumerate(data.get("exclusions", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"excl_{idx}", "exclusion", workflow_id
                    )
            elif section_type.lower() == "definitions" and "definitions" in data:
                for idx, entry in enumerate(data.get("definitions", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"def_{idx}", "definition", workflow_id
                    )
            elif section_type.lower() == "vehicle_schedule" and "vehicles" in data:
                for idx, entry in enumerate(data.get("vehicles", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"veh_{idx}", "vehicle", workflow_id
                    )
            elif section_type.lower() == "driver_schedule" and "drivers" in data:
                for idx, entry in enumerate(data.get("drivers", [])):
                    embeddings_created += await self._process_entry(
                        document_id, section_type, entry, f"drv_{idx}", "driver", workflow_id
                    )
            else:
                # Default case: 1 embedding for the entire section
                embeddings_created += await self._process_entry(
                    document_id, section_type, data, "section_root", "section", workflow_id
                )

        await self.session.commit()
        
        return EmbeddingResult(
            vector_dimension=384,
            chunks_embedded=embeddings_created,
            storage_details={"status": "success", "model": self.model_name}
        )

    async def _process_entry(
        self, 
        document_id: UUID, 
        section_type: str, 
        data: Dict[str, Any],
        entity_id_suffix: str,
        entity_type: str,
        workflow_id: Optional[UUID] = None
    ) -> int:
        """Process a single unit of data, generate embedding and save."""
        try:
            # Generate deterministic text
            text = await self.template_service.run(section_type, data)
            if not text or len(text.strip()) < 10:
                return 0

            # Check if this content has changed (deterministic)
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            
            # Generate ID for the entity
            entity_id = f"{section_type}_{entity_id_suffix}"
            
            # Generate embedding vector
            vector = self.model.encode(text).tolist()
            
            # Extract metadata if available
            eff_date = self.template_service.get_field(data, "policy_period_start")
            exp_date = self.template_service.get_field(data, "policy_period_end")
            loc_id = self.template_service.get_field(data, "location_id")
            
            # Parse dates if they are strings
            if isinstance(eff_date, str):
                try: eff_date = datetime.strptime(eff_date.split("T")[0], "%Y-%m-%d").date()
                except: eff_date = None
            if isinstance(exp_date, str):
                try: exp_date = datetime.strptime(exp_date.split("T")[0], "%Y-%m-%d").date()
                except: exp_date = None

            # Save embedding
            await self.vector_repo.create(
                document_id=document_id,
                section_type=section_type,
                entity_type=entity_type,
                entity_id=entity_id,
                embedding_model=self.model_name,
                embedding_dim=384,
                embedding_version="v1",
                embedding=vector,
                content_hash=content_hash,
                workflow_type=str(workflow_id) if workflow_id else None,
                effective_date=eff_date,
                expiration_date=exp_date,
                location_id=str(loc_id) if loc_id else None,
                status="EMBEDDED",
                embedded_at=datetime.now(timezone.utc)
            )
            return 1
            
        except Exception as e:
            LOGGER.error(f"Failed to process embedding for {section_type}: {e}", exc_info=True)
            return 0
