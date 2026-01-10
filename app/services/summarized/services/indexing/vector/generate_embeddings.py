import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timezone
from abc import ABC, abstractmethod

from sentence_transformers import SentenceTransformer

from app.services.base_service import BaseService
from app.services.summarized.contracts import EmbeddingResult
from app.repositories.vector_embedding_repository import VectorEmbeddingRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.workflow_repository import WorkflowDocumentRepository
from app.services.summarized.services.indexing.vector.vector_template_service import VectorTemplateService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Section Processor Strategy Pattern
class SectionProcessor(ABC):
    """Abstract base class for processing different section types."""
    
    @abstractmethod
    def get_entities(self, data: Dict[str, Any]) -> List[Tuple[Dict[str, Any], str, str]]:
        """Extract entities from section data.
        
        Returns:
            List of tuples: (entity_data, entity_id_suffix, entity_type)
        """
        pass


class ListBasedSectionProcessor(SectionProcessor):
    """Processor for sections containing lists of entities."""
    
    def __init__(self, list_key: str, entity_type: str, id_prefix: str):
        self.list_key = list_key
        self.entity_type = entity_type
        self.id_prefix = id_prefix
    
    def get_entities(self, data: Dict[str, Any]) -> List[Tuple[Dict[str, Any], str, str]]:
        entities = []
        for idx, entry in enumerate(data.get(self.list_key, [])):
            entity_id_suffix = f"{self.id_prefix}_{idx}"
            entities.append((entry, entity_id_suffix, self.entity_type))
        return entities


class SingleSectionProcessor(SectionProcessor):
    """Processor for sections with single entity (entire section)."""
    
    def get_entities(self, data: Dict[str, Any]) -> List[Tuple[Dict[str, Any], str, str]]:
        return [(data, "section_root", "section")]


# Section Processor Factory
class SectionProcessorFactory:
    """Factory for creating appropriate section processors."""
    
    _processors: Dict[str, SectionProcessor] = {}
    _default_processor = SingleSectionProcessor()
    
    @classmethod
    def register(cls, section_type: str, processor: SectionProcessor):
        """Register a processor for a specific section type."""
        cls._processors[section_type.lower()] = processor
    
    @classmethod
    def get_processor(cls, section_type: str) -> SectionProcessor:
        """Get the appropriate processor for a section type."""
        return cls._processors.get(section_type.lower(), cls._default_processor)
    
    @classmethod
    def initialize_default_processors(cls):
        """Register all default section processors."""
        # Register list-based processors
        cls.register("coverages", ListBasedSectionProcessor("coverages", "coverage", "cov"))
        cls.register("loss_run", ListBasedSectionProcessor("claims", "claim", "claim"))
        cls.register("schedule_of_values", ListBasedSectionProcessor("locations", "location", "loc"))
        cls.register("endorsements", ListBasedSectionProcessor("endorsements", "endorsement", "end"))
        cls.register("exclusions", ListBasedSectionProcessor("exclusions", "exclusion", "excl"))
        cls.register("definitions", ListBasedSectionProcessor("definitions", "definition", "def"))
        cls.register("vehicle_schedule", ListBasedSectionProcessor("vehicles", "vehicle", "veh"))
        cls.register("driver_schedule", ListBasedSectionProcessor("drivers", "driver", "drv"))


# Initialize processors on module load
SectionProcessorFactory.initialize_default_processors()


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

    async def run(self, document_id: UUID, workflow_id: UUID) -> EmbeddingResult:
        """Generate and store embeddings for all sections of a document.
        
        Args:
            document_id: UUID of the document to process
            workflow_id: UUID of the workflow
            
        Returns:
            EmbeddingResult with processing statistics
        """
        # 0. Clean up existing embeddings for this document to avoid duplicates
        await self.vector_repo.delete_by_document(document_id)

        # 1. Fetch all section extractions for this document
        sections = await self._fetch_sections(document_id, workflow_id)

        if not sections:
            LOGGER.info(f"No sections found for document {document_id}")
            return EmbeddingResult(
                vector_dimension=384, 
                chunks_embedded=0, 
                storage_details={"status": "no_sections"}
            )

        # 2. Process each section and generate embeddings
        embeddings_created = await self._process_all_sections(sections, document_id, workflow_id)

        await self.session.commit()
        
        return EmbeddingResult(
            vector_dimension=384,
            chunks_embedded=embeddings_created,
            storage_details={"status": "success", "model": self.model_name}
        )

    async def _fetch_sections(self, document_id: UUID) -> List:
        """Fetch section extractions for the document."""
        return await self.section_repo.get_by_document(document_id)

    async def _process_all_sections(
        self, 
        sections: List, 
        document_id: UUID, 
        workflow_id: Optional[UUID]
    ) -> int:
        """Process all sections and return count of embeddings created."""
        embeddings_created = 0
        
        for section in sections:
            section_type = section.section_type
            data = section.extracted_fields
            
            # Use factory to get appropriate processor
            processor = SectionProcessorFactory.get_processor(section_type)
            entities = processor.get_entities(data)
            
            # Process each entity
            for entity_data, entity_id_suffix, entity_type in entities:
                embeddings_created += await self._process_entry(
                    document_id, 
                    workflow_id,
                    section_type, 
                    entity_data, 
                    entity_id_suffix, 
                    entity_type, 
                )
        
        return embeddings_created

    async def _process_entry(
        self, 
        document_id: UUID, 
        workflow_id: UUID,
        section_type: str, 
        data: Dict[str, Any],
        entity_id_suffix: str,
        entity_type: str,
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
            
            # Extract and parse metadata
            metadata = self._extract_metadata(data)
            
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
                workflow_id=workflow_id,
                effective_date=metadata["effective_date"],
                expiration_date=metadata["expiration_date"],
                location_id=metadata["location_id"],
                status="EMBEDDED",
                embedded_at=datetime.now(timezone.utc)
            )
            return 1
            
        except Exception as e:
            LOGGER.error(f"Failed to process embedding for {section_type}: {e}", exc_info=True)
            return 0

    def _extract_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and parse metadata from entity data."""
        eff_date = self.template_service.get_field(data, "policy_period_start")
        exp_date = self.template_service.get_field(data, "policy_period_end")
        loc_id = self.template_service.get_field(data, "location_id")
        
        # Parse dates if they are strings
        if isinstance(eff_date, str):
            try:
                eff_date = datetime.strptime(eff_date.split("T")[0], "%Y-%m-%d").date()
            except:
                eff_date = None
        
        if isinstance(exp_date, str):
            try:
                exp_date = datetime.strptime(exp_date.split("T")[0], "%Y-%m-%d").date()
            except:
                exp_date = None
        
        return {
            "effective_date": eff_date,
            "expiration_date": exp_date,
            "location_id": str(loc_id) if loc_id else None
        }