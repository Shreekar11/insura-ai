"""Proposal-focused comparison service for generating insurance proposals.

This service provides focused comparison logic for proposal-relevant sections,
and detects document roles (expiring vs. renewal) based on extracted data.
"""

from typing import Dict, List, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.product.proposal_generation.canonical_mapping_service import CanonicalMappingService
from app.repositories.step_repository import StepSectionOutputRepository, StepEntityOutputRepository
from app.services.product.policy_comparison.entity_comparison_service import EntityComparisonService
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.product.policy_comparison import ComparisonChange, EntityComparisonResult
from app.schemas.product.extracted_data import SECTION_DATA_MODELS
from app.services.product.proposal_generation.proposal_reasoning_service import ProposalReasoningService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

# Sections relevant to proposal generation
PROPOSAL_SECTIONS = [
    "declarations",
    "coverages",
    "deductibles",
    "premium",
    "conditions",
    "exclusions",
    "endorsements",
]

# Map section types to entity types for fallback
SECTION_ENTITY_MAP = {
    "coverages": "Coverage",
    "deductibles": "Deductible",
    "exclusions": "Exclusion",
    "endorsements": "Endorsement",
    "declarations": "Policy",
    "conditions": "Condition",
}


class ProposalComparisonService:
    """Service for comparing documents specifically for proposal generation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = StepSectionOutputRepository(session)
        self.entity_repo = StepEntityOutputRepository(session)
        self.canonical_mapper = CanonicalMappingService()
        self.reasoning_service = ProposalReasoningService()
        self.entity_comparison_service = EntityComparisonService(session)
        self.workflow_repo = WorkflowRepository(session)

    async def detect_document_roles(
        self,
        workflow_id: UUID,
        document_ids: List[UUID],
    ) -> Dict[str, Any]:
        """Detect document roles (1 expiring, N renewals).
        
        Args:
            workflow_id: Workflow ID
            document_ids: List of document IDs
            
        Returns:
            Dict with 'expiring' (UUID) and 'renewals' (List[UUID])
        """
        if not document_ids:
            return {"expiring": None, "renewals": []}

        doc_metadata = []
        for doc_id in document_ids:
            declarations = await self.section_repo.get_by_document_and_section(
                document_id=doc_id, section_type="declarations"
            )
            
            effective_date = None
            quote_type = None
            if declarations and declarations.display_payload:
                payload = declarations.display_payload
                quote_type = payload.get("quote_type", "").lower()
                date_str = payload.get("effective_date")
                if date_str:
                    try:
                        effective_date = datetime.strptime(str(date_str), "%Y-%m-%d")
                    except ValueError:
                        pass
            
            doc_metadata.append({
                "document_id": doc_id,
                "effective_date": effective_date,
                "quote_type": quote_type,
            })

        # Logic: 
        # 1. Any doc with quote_type='expiring' is the one.
        # 2. Otherwise, the oldest effective_date is expiring.
        # 3. Everything else is a renewal.
        
        expiring_doc = None
        # Priority 1: quote_type
        for doc in doc_metadata:
            if doc["quote_type"] == "expiring":
                expiring_doc = doc
                break
        
        # Priority 2: Oldest date
        if not expiring_doc:
            dated_docs = [d for d in doc_metadata if d["effective_date"]]
            if dated_docs:
                expiring_doc = min(dated_docs, key=lambda x: x["effective_date"])
        
        # Priority 3: First one
        if not expiring_doc:
            expiring_doc = doc_metadata[0]

        renewals = [d["document_id"] for d in doc_metadata if d["document_id"] != expiring_doc["document_id"]]
        
        return {
            "expiring": expiring_doc["document_id"],
            "renewals": renewals,
        }

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
            # Get and normalize section data for both documents
            expiring_data = await self._fetch_and_normalize_data(
                document_id=expiring_doc_id,
                workflow_id=workflow_id,
                section_type=section_type
            )
            renewal_data = await self._fetch_and_normalize_data(
                document_id=renewal_doc_id,
                workflow_id=workflow_id,
                section_type=section_type
            )
            
            # Compare section fields
            section_changes = self._compare_section_fields(
                section_type=section_type,
                expiring_data=expiring_data,
                renewal_data=renewal_data,
            )
            changes.extend(section_changes)
        
        # Enrich changes with LLM reasoning
        if changes:
            try:
                changes = await self.reasoning_service.enrich_changes_with_reasoning(changes)
            except Exception as e:
                LOGGER.error(f"Failed to enrich proposal changes with reasoning: {e}")
        
        return changes

    async def execute_entity_comparison(
        self,
        workflow_id: UUID,
        expiring_doc_id: UUID,
        renewal_doc_id: UUID,
        expiring_doc_name: str,
        renewal_doc_name: str,
    ) -> EntityComparisonResult:
        """Execute entity-level comparison for frontend display."""
        # 1. Fetch extracted data for both documents
        expiring_data = await self._get_extracted_data_for_comparison(expiring_doc_id, workflow_id)
        renewal_data = await self._get_extracted_data_for_comparison(renewal_doc_id, workflow_id)
        
        # 2. Execute entity comparison
        result = await self.entity_comparison_service.compare_entities(
            workflow_id=workflow_id,
            doc1_id=expiring_doc_id,
            doc2_id=renewal_doc_id,
            doc1_data=expiring_data,
            doc2_data=renewal_data,
        )
        
        # 3. Emit comparison:completed event
        await self._emit_comparison_completed_event(workflow_id, result, expiring_doc_name, renewal_doc_name)
        
        return result

    async def _get_extracted_data_for_comparison(self, document_id: UUID, workflow_id: UUID) -> Dict[str, Any]:
        """Helper to fetch and format extracted data for entity comparison."""
        entities = await self.entity_repo.get_by_document(document_id, workflow_id=workflow_id)
        sections = await self.section_repo.get_by_document(document_id)
        
        coverages = []
        exclusions = []
        
        for entity in entities:
            if not entity.display_payload:
                continue
            payload = entity.display_payload
            if entity.entity_type.lower() == "coverage":
                if isinstance(payload, list):
                    coverages.extend(payload)
                elif isinstance(payload, dict):
                    coverages.append(payload)
            elif entity.entity_type.lower() == "exclusion":
                if isinstance(payload, list):
                    exclusions.extend(payload)
                elif isinstance(payload, dict):
                    exclusions.append(payload)
        
        # Also check sections for effective_coverages/exclusions
        for section in sections:
            if not section.display_payload:
                continue
            payload = section.display_payload
            if section.section_type == "effective_coverages":
                if isinstance(payload, list):
                    coverages.extend(payload)
                elif isinstance(payload, dict):
                    coverages.append(payload)
            elif section.section_type == "effective_exclusions":
                if isinstance(payload, list):
                    exclusions.extend(payload)
                elif isinstance(payload, dict):
                    exclusions.append(payload)
                    
        return {
            "entities": [e.display_payload for e in entities if e.display_payload],
            "sections": [s.display_payload for s in sections if s.display_payload],
            "effective_coverages": coverages,
            "effective_exclusions": exclusions,
        }

    async def _emit_comparison_completed_event(
        self,
        workflow_id: UUID,
        result: EntityComparisonResult,
        doc1_name: str,
        doc2_name: str,
    ) -> None:
        """Emit a comparison:completed SSE event."""
        event_payload = {
            "stage_name": "entity_comparison",
            "status": "completed",
            "message": f"Comparison between {doc1_name} and {doc2_name}",
            "has_comparison": True,
            "comparison_summary": {
                "coverage_matches": result.summary.coverage_matches,
                "exclusion_matches": result.summary.exclusion_matches,
                "total_added": result.summary.coverages_added + result.summary.exclusions_added,
                "total_removed": result.summary.coverages_removed + result.summary.exclusions_removed,
                "total_modified": result.summary.coverage_partial_matches + result.summary.exclusion_partial_matches,
            },
            "overall_confidence": float(result.overall_confidence),
            "overall_explanation": result.overall_explanation,
        }

        await self.workflow_repo.emit_run_event(
            workflow_id=workflow_id,
            event_type="comparison:completed",
            payload=event_payload,
        )
        await self.session.commit()


    async def _fetch_and_normalize_data(
        self,
        document_id: UUID,
        workflow_id: UUID,
        section_type: str
    ) -> Dict[str, Any]:
        """Fetch data from section repo or entity repo as fallback, then normalize."""
        # 1. Try fetching from section repository
        section_output = await self.section_repo.get_by_document_and_section(
            document_id=document_id,
            section_type=section_type
        )
        
        raw_data = section_output.display_payload if section_output else {}
        
        # 2. Check if we need fallback to entities
        # Usually section data is a dict like {"coverages": []} or {"endorsements": []} if empty
        is_empty = not raw_data
        if not is_empty and isinstance(raw_data, dict):
            # Check for empty lists in common keys
            for key in ["coverages", "deductibles", "exclusions", "endorsements", "conditions", "fields"]:
                if key in raw_data and (raw_data[key] is None or (isinstance(raw_data[key], list) and not raw_data[key])):
                    is_empty = True
                    break
        
        if is_empty:
            entity_type = SECTION_ENTITY_MAP.get(section_type)
            if entity_type:
                entities = await self.entity_repo.get_by_document_and_type(
                    document_id=document_id,
                    entity_type=entity_type,
                    workflow_id=workflow_id
                )
                if entities:
                    # Transform entity list into a format similar to section output for normalization
                    if section_type == "coverages":
                        raw_data = {"coverages": [e.display_payload.get("attributes", {}) for e in entities]}
                    elif section_type == "deductibles":
                        raw_data = {"deductibles": [e.display_payload.get("attributes", {}) for e in entities]}
                    elif section_type == "exclusions":
                        raw_data = {"exclusions": [e.display_payload.get("attributes", {}) for e in entities]}
                    elif section_type == "endorsements":
                        raw_data = {"endorsements": [e.display_payload.get("attributes", {}) for e in entities]}
                    elif section_type == "declarations":
                        # Merge all Policy entity attributes (usually just one)
                        merged_policy = {}
                        for e in entities:
                            merged_policy.update(e.display_payload.get("attributes", {}))
                        raw_data = {"fields": merged_policy} if merged_policy else {}

        # 3. Normalize to flat key-value pairs
        return self._normalize_section_data(section_type, raw_data)

    def _normalize_section_data(self, section_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize structured section data into flat comparable key-value pairs using Pydantic schemas."""
        if not data:
            return {}
            
        flat_data = {}
        model_class = SECTION_DATA_MODELS.get(section_type)
        
        if section_type == "coverages":
            items = data.get("coverages", [])
            for item in items:
                try:
                    # Validate item using Pydantic model
                    validated = model_class(**item) if model_class else item
                    name = validated.coverage_name if hasattr(validated, "coverage_name") else (item.get("coverage_name") or item.get("id"))
                    
                    if not name:
                        continue
                        
                    # Handle limits, deductibles, premiums from validated model
                    if hasattr(validated, "limit_amount") and validated.limit_amount is not None:
                        flat_data[name] = validated.limit_amount
                    if hasattr(validated, "deductible_amount") and validated.deductible_amount is not None:
                        flat_data[f"{name} Deductible"] = validated.deductible_amount
                    if hasattr(validated, "premium_amount") and validated.premium_amount is not None:
                        flat_data[f"{name} Premium"] = validated.premium_amount
                except Exception as e:
                    LOGGER.error(f"Validation error in coverages for {item}: {e}")
                    # Fallback to raw item if validation fails
                    name = item.get("coverage_name") or item.get("id")
                    if name:
                        flat_data[name] = item.get("limit_amount")
                    
        elif section_type == "deductibles":
            items = data.get("deductibles", [])
            for item in items:
                try:
                    validated = model_class(**item) if model_class else item
                    name = validated.deductible_name if hasattr(validated, "deductible_name") else (item.get("deductible_name") or item.get("id"))
                    if name:
                        flat_data[name] = validated.amount if hasattr(validated, "amount") else item.get("amount")
                except Exception as e:
                    LOGGER.error(f"Validation error in deductibles for {item}: {e}")
                    name = item.get("deductible_name") or item.get("id")
                    if name:
                        flat_data[name] = item.get("amount")
                    
        elif section_type == "exclusions":
            items = data.get("exclusions", [])
            for item in items:
                try:
                    validated = model_class(**item) if model_class else item
                    name = validated.title if hasattr(validated, "title") else (item.get("title") or item.get("id"))
                    if name:
                        flat_data[name] = "Present"
                except Exception as e:
                    LOGGER.error(f"Validation error in exclusions for {item}: {e}")
                    name = item.get("title") or item.get("id")
                    if name:
                        flat_data[name] = "Present"
                    
        elif section_type == "endorsements":
            items = data.get("endorsements", [])
            for item in items:
                try:
                    validated = model_class(**item) if model_class else item
                    name = validated.endorsement_name if hasattr(validated, "endorsement_name") else (item.get("endorsement_name") or item.get("id"))
                    if name:
                        flat_data[name] = "Present"
                except Exception as e:
                    LOGGER.error(f"Validation error in endorsements for {item}: {e}")
                    name = item.get("endorsement_name") or item.get("id")
                    if name:
                        flat_data[name] = "Present"
                    
        elif section_type == "declarations":
            # Declarations ('fields') is usually a single object
            fields = data.get("fields", data)
            try:
                validated = model_class(**fields) if model_class else fields
                # Return dict representation of validated fields
                flat_data = validated.model_dump() if hasattr(validated, "model_dump") else fields
            except Exception as e:
                LOGGER.error(f"Validation error in declarations: {e}")
                flat_data = fields
            
        else:
            # For other sections (like premium), just try to validate as a whole if model exists
            try:
                if model_class:
                    validated = model_class(**data)
                    flat_data = validated.model_dump()
                else:
                    flat_data = data
            except Exception as e:
                LOGGER.error(f"Validation error in {section_type}: {e}")
                flat_data = data
            
        return flat_data

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
            canonical_name = self.canonical_mapper.get_canonical_name(section_type, field_name)
            
            from app.schemas.product.policy_comparison import SectionProvenance
            dummy_provenance = SectionProvenance(
                doc1_section_id=UUID("00000000-0000-0000-0000-000000000000"),
                doc2_section_id=UUID("00000000-0000-0000-0000-000000000000")
            )

            change = ComparisonChange(
                section_type=section_type,
                field_name=field_name,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
                change_type=self._get_change_type(old_value, new_value),
                severity="info",
                delta_type=delta_type,
                delta_flag=delta_flag,
                canonical_coverage_name=canonical_name,
                provenance=dummy_provenance
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
