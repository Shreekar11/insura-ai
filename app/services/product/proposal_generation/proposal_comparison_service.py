"""Proposal-focused comparison service for generating insurance proposals.

This service provides focused comparison logic for proposal-relevant sections,
and detects document roles (expiring vs. renewal) based on extracted data.
"""

from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product.proposal_generation.canonical_mapping_service import CanonicalMappingService
from app.repositories.step_repository import StepSectionOutputRepository
from app.schemas.product.policy_comparison import ComparisonChange
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Sections relevant to proposal generation
PROPOSAL_SECTIONS = [
    "declarations",
    "coverages",
    "deductibles",
    "premium",
    "exclusions",
    "endorsements",
]


class ProposalComparisonService:
    """Service for comparing documents specifically for proposal generation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = StepSectionOutputRepository(session)
        self.canonical_mapper = CanonicalMappingService()

    async def detect_document_roles(
        self,
        workflow_id: UUID,
        document_ids: List[UUID],
    ) -> Dict[str, UUID]:
        """Detect which document is expiring vs. renewal.
        
        Detection logic:
        1. Check `quote_type` field in Declarations (if available)
        2. Compare `effective_date` - earlier date is expiring
        
        Args:
            workflow_id: Workflow ID for fetching extractions
            document_ids: List of exactly 2 document IDs
            
        Returns:
            Dict with keys 'expiring' and 'renewal' mapping to document IDs
        """
        if len(document_ids) != 2:
            raise ValueError("Exactly 2 documents required for proposal comparison")

        doc_metadata = []
        
        for doc_id in document_ids:
            # Fetch declarations section for this document
            declarations = await self.section_repo.get_by_document_and_section(
                document_id=doc_id,
                workflow_id=workflow_id,
                section_type="declarations"
            )
            
            effective_date = None
            quote_type = None
            
            if declarations and declarations.display_payload:
                payload = declarations.display_payload
                
                # Try to get quote_type
                quote_type = payload.get("quote_type", "").lower()
                
                # Try to get effective_date
                date_str = payload.get("effective_date") or payload.get("policy_effective_date")
                if date_str:
                    try:
                        effective_date = datetime.strptime(str(date_str), "%Y-%m-%d")
                    except ValueError:
                        LOGGER.warning(f"Could not parse date: {date_str}")
            
            doc_metadata.append({
                "document_id": doc_id,
                "effective_date": effective_date,
                "quote_type": quote_type,
            })

        # Detection logic
        doc1, doc2 = doc_metadata
        
        # Priority 1: Check quote_type
        if doc1["quote_type"] == "expiring" or doc2["quote_type"] == "renewal":
            return {"expiring": doc1["document_id"], "renewal": doc2["document_id"]}
        if doc2["quote_type"] == "expiring" or doc1["quote_type"] == "renewal":
            return {"expiring": doc2["document_id"], "renewal": doc1["document_id"]}
        
        # Priority 2: Compare effective dates
        if doc1["effective_date"] and doc2["effective_date"]:
            if doc1["effective_date"] < doc2["effective_date"]:
                return {"expiring": doc1["document_id"], "renewal": doc2["document_id"]}
            else:
                return {"expiring": doc2["document_id"], "renewal": doc1["document_id"]}
        
        # Default: First document is expiring
        LOGGER.warning("Could not determine document roles, defaulting to order")
        return {"expiring": doc1["document_id"], "renewal": doc2["document_id"]}

    async def compare_for_proposal(
        self,
        workflow_id: UUID,
        expiring_doc_id: UUID,
        renewal_doc_id: UUID,
    ) -> List[ComparisonChange]:
        """Compare two documents focusing on proposal-relevant sections.
        
        Args:
            workflow_id: Workflow ID
            expiring_doc_id: Document ID of expiring policy
            renewal_doc_id: Document ID of renewal quote
            
        Returns:
            List of ComparisonChange objects with delta_type and delta_flag
        """
        changes: List[ComparisonChange] = []
        
        for section_type in PROPOSAL_SECTIONS:
            # Get section data for both documents
            expiring_section = await self.section_repo.get_by_document_and_section(
                document_id=expiring_doc_id,
                workflow_id=workflow_id,
                section_type=section_type
            )
            renewal_section = await self.section_repo.get_by_document_and_section(
                document_id=renewal_doc_id,
                workflow_id=workflow_id,
                section_type=section_type
            )
            
            expiring_data = expiring_section.display_payload if expiring_section else {}
            renewal_data = renewal_section.display_payload if renewal_section else {}
            
            # Compare section fields
            section_changes = self._compare_section_fields(
                section_type=section_type,
                expiring_data=expiring_data,
                renewal_data=renewal_data,
            )
            changes.extend(section_changes)
        
        return changes

    def _compare_section_fields(
        self,
        section_type: str,
        expiring_data: Dict[str, Any],
        renewal_data: Dict[str, Any],
    ) -> List[ComparisonChange]:
        """Compare fields within a section and return changes with delta flags."""
        changes = []
        all_keys = set(expiring_data.keys()) | set(renewal_data.keys())
        
        for field_name in all_keys:
            old_value = expiring_data.get(field_name)
            new_value = renewal_data.get(field_name)
            
            # Skip metadata fields
            if field_name.startswith("_") or field_name in ["id", "created_at", "updated_at"]:
                continue
            
            # Determine delta type and flag
            delta_type, delta_flag = self._calculate_delta(field_name, old_value, new_value, section_type)
            
            # Canonical name lookup
            canonical_name = None
            if section_type == "coverages":
                canonical_name = self.canonical_mapper.get_canonical_coverage_name(field_name)
            
            change = ComparisonChange(
                section=section_type,
                field=field_name,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
                change_type=self._get_change_type(old_value, new_value),
                severity="info",
                delta_type=delta_type,
                delta_flag=delta_flag,
                canonical_coverage_name=canonical_name,
            )
            changes.append(change)
        
        return changes

    def _calculate_delta(
        self,
        field_name: str,
        old_value: Any,
        new_value: Any,
        section_type: str,
    ) -> Tuple[str, str]:
        """Calculate strategic delta type and flag for a field change."""
        field_lower = field_name.lower()
        is_limit = "limit" in field_lower or "amount" in field_lower
        is_deductible = "deductible" in field_lower or "retention" in field_lower or "sir" in field_lower
        is_premium = "premium" in field_lower or "cost" in field_lower or "price" in field_lower
        
        # Handle GAP (coverage removed)
        if old_value is not None and new_value is None:
            return "GAP", "NEGATIVE"
        
        # Handle ADVANTAGE (coverage added)
        if old_value is None and new_value is not None:
            return "ADVANTAGE", "POSITIVE"
        
        # Handle numeric comparisons
        try:
            old_num = float(str(old_value).replace(",", "").replace("$", "")) if old_value else None
            new_num = float(str(new_value).replace(",", "").replace("$", "")) if new_value else None
            
            if old_num is not None and new_num is not None:
                if new_num > old_num:
                    if is_limit:
                        return "POSITIVE_CHANGE", "POSITIVE"
                    elif is_deductible or is_premium:
                        return "NEGATIVE_CHANGE", "NEGATIVE"
                elif new_num < old_num:
                    if is_limit:
                        return "NEGATIVE_CHANGE", "NEGATIVE"
                    elif is_deductible or is_premium:
                        return "POSITIVE_CHANGE", "POSITIVE"
        except (ValueError, TypeError):
            pass
        
        # Default for text changes
        if old_value != new_value:
            return "MODIFIED", "NEUTRAL"
        
        return "UNCHANGED", "NEUTRAL"

    def _get_change_type(self, old_value: Any, new_value: Any) -> str:
        """Get basic change type."""
        if old_value is None and new_value is not None:
            return "added"
        if old_value is not None and new_value is None:
            return "removed"
        if old_value != new_value:
            return "modified"
        return "unchanged"
