"""Pre-flight validation service for Policy Comparison workflow."""

from uuid import UUID
from typing import Optional
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.config.policy_comparison_config import (
    REQUIRED_SECTIONS,
    REQUIRED_ENTITIES,
    INSURED_NAME_MATCH_THRESHOLD,
)
from app.repositories.document_repository import DocumentRepository
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.entity_repository import EntityMentionRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class PreflightValidator:
    """Validates documents before starting policy comparison.
    
    Ensures that documents meet all requirements for comparison:
    - Exactly 2 documents
    - Both classified as 'policy' type
    - Same insured name (fuzzy match)
    - Required sections present
    - Required entities extracted
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.document_repo = DocumentRepository(session)
        self.section_repo = SectionExtractionRepository(session)
        self.entity_repo = EntityMentionRepository(session)

    async def validate_documents(
        self, document_ids: list[UUID], workflow_id: UUID
    ) -> dict:
        """Run all pre-flight validation checks.
        
        Args:
            document_ids: List of document UUIDs to validate
            workflow_id: Workflow ID for context
            
        Returns:
            Dictionary with validation results and document metadata
            
        Raises:
            ValidationError: If any validation check fails
        """
        LOGGER.info(
            f"Starting pre-flight validation for workflow {workflow_id}",
            extra={"workflow_id": str(workflow_id), "document_ids": [str(d) for d in document_ids]}
        )

        # 1. Validate document count
        self._validate_document_count(document_ids)

        # 2. Fetch documents
        documents = await self._fetch_documents(document_ids)

        # 3. Validate document types
        self._validate_document_types(documents)

        # 4. Validate same insured
        await self._validate_same_insured(documents, workflow_id)

        # 5. Validate required sections
        await self._validate_required_sections(documents, workflow_id)

        # 6. Validate required entities
        await self._validate_required_entities(documents, workflow_id)

        LOGGER.info(
            f"Pre-flight validation passed for workflow {workflow_id}",
            extra={"workflow_id": str(workflow_id)}
        )

        return {
            "validation_passed": True,
            "documents": [
                {
                    "document_id": str(doc.id),
                    "document_type": doc.document_type,
                    "filename": doc.filename,
                }
                for doc in documents
            ],
        }

    def _validate_document_count(self, document_ids: list[UUID]) -> None:
        """Validate exactly 2 documents provided."""
        if len(document_ids) != 2:
            raise ValidationError(
                f"Policy comparison requires exactly 2 documents, got {len(document_ids)}"
            )

    async def _fetch_documents(self, document_ids: list[UUID]) -> list:
        """Fetch documents from database."""
        documents = []
        for doc_id in document_ids:
            doc = await self.document_repo.get_by_id(doc_id)
            if not doc:
                raise ValidationError(f"Document {doc_id} not found")
            documents.append(doc)
        return documents

    def _validate_document_types(self, documents: list) -> None:
        """Validate both documents are classified as 'policy' type."""
        for doc in documents:
            if doc.document_type != "policy":
                raise ValidationError(
                    f"Document {doc.id} is not a policy document (type: {doc.document_type})"
                )

    async def _validate_same_insured(
        self, documents: list, workflow_id: UUID
    ) -> None:
        """Validate documents have the same insured name using fuzzy matching."""
        insured_names = []

        for doc in documents:
            # Fetch INSURED_NAME entity from section extractions
            insured_name = await self._extract_insured_name(doc.id, workflow_id)
            if not insured_name:
                raise ValidationError(
                    f"Document {doc.id} missing INSURED_NAME entity"
                )
            insured_names.append(insured_name)

        # Fuzzy match insured names
        similarity = fuzz.ratio(insured_names[0].lower(), insured_names[1].lower()) / 100.0

        if similarity < INSURED_NAME_MATCH_THRESHOLD:
            raise ValidationError(
                f"Insured names do not match: '{insured_names[0]}' vs '{insured_names[1]}' "
                f"(similarity: {similarity:.2f}, threshold: {INSURED_NAME_MATCH_THRESHOLD})"
            )

        LOGGER.info(
            f"Insured name match validated: {insured_names[0]} (similarity: {similarity:.2f})"
        )

    async def _validate_required_sections(
        self, documents: list, workflow_id: UUID
    ) -> None:
        """Validate required sections are present in both documents."""
        for doc in documents:
            sections = await self.section_repo.get_by_document_and_workflow(
                doc.id, workflow_id
            )
            section_types = {s.section_type for s in sections}

            missing_sections = set(REQUIRED_SECTIONS) - section_types
            if missing_sections:
                raise ValidationError(
                    f"Document {doc.id} missing required sections: {missing_sections}"
                )

        LOGGER.info(f"Required sections validated: {REQUIRED_SECTIONS}")

    async def _validate_required_entities(
        self, documents: list, workflow_id: UUID
    ) -> None:
        """Validate required entities are extracted from both documents."""
        for doc in documents:
            # Get all entity mentions for this document
            entities = await self.entity_repo.get_by_document_id(doc.id)
            entity_types = {e.entity_type for e in entities}

            missing_entities = set(REQUIRED_ENTITIES) - entity_types
            if missing_entities:
                raise ValidationError(
                    f"Document {doc.id} missing required entities: {missing_entities}"
                )

        LOGGER.info(f"Required entities validated: {REQUIRED_ENTITIES}")

    async def _extract_insured_name(
        self, document_id: UUID, workflow_id: UUID
    ) -> Optional[str]:
        """Extract insured name from section extractions.
        
        Looks for INSURED_NAME in declarations section or entity mentions.
        """
        # Try to get from declarations section first
        sections = await self.section_repo.get_by_document_and_workflow(
            document_id, workflow_id
        )

        for section in sections:
            if section.section_type == "declarations":
                extracted_fields = section.extracted_fields
                # Try various field names
                for field_name in ["insured_name", "insured", "named_insured"]:
                    if field_name in extracted_fields:
                        return extracted_fields[field_name]

        # Fallback: get from entity mentions
        entities = await self.entity_repo.get_by_document_id(document_id)
        for entity in entities:
            if entity.entity_type == "INSURED_NAME":
                return entity.mention_text

        return None
