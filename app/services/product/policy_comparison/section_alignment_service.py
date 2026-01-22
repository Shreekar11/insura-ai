"""Section alignment service for Policy Comparison workflow."""

from uuid import UUID
from typing import Optional
from decimal import Decimal
from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.schemas.product.policy_comparison import SectionAlignment
from app.temporal.product.policy_comparison.configs.policy_comparison import (
    ALIGNMENT_CONFIDENCE_THRESHOLD,
    COVERAGE_NAME_MATCH_THRESHOLD,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class SectionAlignmentService:
    """Service for aligning sections across two policy documents.
    
    Handles alignment of:
    - Declarations (1:1 direct alignment)
    - Coverages (match by coverage name/type)
    - Other sections (direct type matching)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = SectionExtractionRepository(session)

    async def align_sections(
        self,
        doc1_id: UUID,
        doc2_id: UUID,
        workflow_id: UUID,
        section_types: list[str],
    ) -> list[SectionAlignment]:
        """Align sections across two documents.
        
        Args:
            doc1_id: First document UUID
            doc2_id: Second document UUID
            workflow_id: Workflow UUID for context
            section_types: List of section types to align
            
        Returns:
            List of SectionAlignment objects
        """
        LOGGER.info(
            f"Aligning sections for documents {doc1_id} and {doc2_id}",
            extra={
                "doc1_id": str(doc1_id),
                "doc2_id": str(doc2_id),
                "section_types": section_types,
            }
        )

        alignments = []

        for section_type in section_types:
            if section_type == "declarations":
                alignment = await self._align_declarations(doc1_id, doc2_id, workflow_id)
            elif section_type == "coverages":
                coverage_alignments = await self._align_coverages(doc1_id, doc2_id, workflow_id)
                alignments.extend(coverage_alignments)
                continue
            else:
                alignment = await self._align_generic_section(
                    doc1_id, doc2_id, workflow_id, section_type
                )

            if alignment:
                alignments.append(alignment)

        LOGGER.info(
            f"Section alignment completed: {len(alignments)} alignments created",
            extra={"alignment_count": len(alignments)}
        )

        return alignments

    async def _align_declarations(
        self, doc1_id: UUID, doc2_id: UUID, workflow_id: UUID
    ) -> Optional[SectionAlignment]:
        """Align declarations sections (1:1 direct alignment).
        
        Declarations section is unique per document, so this is a direct match.
        """
        doc1_sections = await self.section_repo.get_by_document_and_workflow(
            doc1_id, workflow_id
        )
        doc2_sections = await self.section_repo.get_by_document_and_workflow(
            doc2_id, workflow_id
        )

        doc1_decl = next((s for s in doc1_sections if s.section_type == "declarations"), None)
        doc2_decl = next((s for s in doc2_sections if s.section_type == "declarations"), None)

        if not doc1_decl or not doc2_decl:
            LOGGER.warning("Declarations section missing in one or both documents")
            return None

        return SectionAlignment(
            section_type="declarations",
            doc1_section_id=doc1_decl.id,
            doc2_section_id=doc2_decl.id,
            alignment_confidence=Decimal("1.0"),
            alignment_method="direct",
        )

    async def _align_coverages(
        self, doc1_id: UUID, doc2_id: UUID, workflow_id: UUID
    ) -> list[SectionAlignment]:
        """Align coverage sections by coverage name/type.
        
        Coverages may have multiple entries per document, so we match by name.
        """
        doc1_sections = await self.section_repo.get_by_document_and_workflow(
            doc1_id, workflow_id
        )
        doc2_sections = await self.section_repo.get_by_document_and_workflow(
            doc2_id, workflow_id
        )

        doc1_coverages = [s for s in doc1_sections if s.section_type == "coverages"]
        doc2_coverages = [s for s in doc2_sections if s.section_type == "coverages"]

        alignments = []

        # For now, if there's only one coverage section per document, do direct alignment
        # In Phase 2, we'll implement coverage-level matching using canonical entities
        if len(doc1_coverages) == 1 and len(doc2_coverages) == 1:
            alignments.append(
                SectionAlignment(
                    section_type="coverages",
                    doc1_section_id=doc1_coverages[0].id,
                    doc2_section_id=doc2_coverages[0].id,
                    alignment_confidence=Decimal("1.0"),
                    alignment_method="direct",
                )
            )
        else:
            # Multiple coverage sections - match by coverage name
            for doc1_cov in doc1_coverages:
                best_match = self._find_best_coverage_match(doc1_cov, doc2_coverages)
                if best_match:
                    alignments.append(best_match)

        return alignments

    def _find_best_coverage_match(
        self, source_coverage, target_coverages: list
    ) -> Optional[SectionAlignment]:
        """Find best matching coverage using fuzzy string matching.
        
        Matches based on coverage name/type extracted from section fields.
        """
        source_name = self._extract_coverage_name(source_coverage)
        if not source_name:
            return None

        best_match = None
        best_score = 0.0

        for target_coverage in target_coverages:
            target_name = self._extract_coverage_name(target_coverage)
            if not target_name:
                continue

            # Fuzzy match coverage names
            score = fuzz.ratio(source_name.lower(), target_name.lower()) / 100.0

            if score > best_score and score >= COVERAGE_NAME_MATCH_THRESHOLD:
                best_score = score
                best_match = target_coverage

        if best_match:
            return SectionAlignment(
                section_type="coverages",
                doc1_section_id=source_coverage.id,
                doc2_section_id=best_match.id,
                alignment_confidence=Decimal(str(best_score)),
                alignment_method="fuzzy_match",
            )

        return None

    def _extract_coverage_name(self, coverage_section) -> Optional[str]:
        """Extract coverage name from section extracted_fields.
        
        Tries multiple field names to find coverage identifier.
        """
        fields = coverage_section.extracted_fields
        for field_name in ["coverage_name", "coverage_type", "name", "type"]:
            if field_name in fields:
                return str(fields[field_name])
        return None

    async def _align_generic_section(
        self, doc1_id: UUID, doc2_id: UUID, workflow_id: UUID, section_type: str
    ) -> Optional[SectionAlignment]:
        """Align generic section types (endorsements, exclusions, etc.).
        
        For Phase 1, we do simple 1:1 alignment by section type.
        Phase 2 will add semantic matching for clause-level alignment.
        """
        doc1_sections = await self.section_repo.get_by_document_and_workflow(
            doc1_id, workflow_id
        )
        doc2_sections = await self.section_repo.get_by_document_and_workflow(
            doc2_id, workflow_id
        )

        doc1_section = next((s for s in doc1_sections if s.section_type == section_type), None)
        doc2_section = next((s for s in doc2_sections if s.section_type == section_type), None)

        if not doc1_section or not doc2_section:
            LOGGER.warning(f"Section {section_type} missing in one or both documents")
            return None

        return SectionAlignment(
            section_type=section_type,
            doc1_section_id=doc1_section.id,
            doc2_section_id=doc2_section.id,
            alignment_confidence=Decimal("1.0"),
            alignment_method="direct",
        )
