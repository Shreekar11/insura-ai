"""Service for assembling a full proposal from comparison results."""

from typing import List, Dict, Any
from uuid import UUID, uuid4
from app.schemas.product.policy_comparison import ComparisonChange
from app.schemas.product.proposal_generation import (
    Proposal, 
    ProposalSection, 
    ProposalComparisonRow
)
from app.services.product.proposal_generation.narrative_service import ProposalNarrativeService
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class ProposalAssemblyService:
    """Orchestrates the assembly of a Proposal object.
    
    Coordinates between comparison data, narrative generation, 
    and document metadata.
    """
    
    def __init__(self, narrative_service: ProposalNarrativeService):
        self.narrative_service = narrative_service

    async def assemble_proposal(
        self,
        workflow_id: UUID,
        document_ids: List[UUID],
        all_changes: Dict[str, List[ComparisonChange]],
        metadata: Dict[str, Any] = None
    ) -> Proposal:
        """Assemble a complete Proposal object with multi-quote support."""
        
        # 1. Group changes by section across ALL renewals
        section_groups = {}
        for doc_id, changes in all_changes.items():
            for c in changes:
                if c.section_type not in section_groups:
                    section_groups[c.section_type] = []
                # Tag change with source doc_id if needed, but for sections we just need the text
                section_groups[c.section_type].append(c)

        # 2. Generate sections and narratives (uses primary renewal for now or aggregate)
        proposal_sections = []
        global_hitl_items = []
        
        for section_type, section_changes in section_groups.items():
            # Use narrative service on the full list of changes across all quotes
            narrative = await self.narrative_service.generate_section_narrative(
                section_type, 
                section_changes
            )
            
            key_findings = []
            section_hitl_needed = False
            
            for c in section_changes:
                if c.delta_type in ["GAP", "ADVANTAGE", "NEGATIVE_CHANGE"]:
                    key_findings.append({
                        "field": c.field_name, 
                        "delta": c.delta_type, 
                        "coverage": c.coverage_name,
                        "reasoning": c.reasoning
                    })
                    if c.delta_type == "GAP":
                        section_hitl_needed = True
                        global_hitl_items.append(f"GAP in {section_type}")

            proposal_sections.append(ProposalSection(
                section_type=section_type,
                title=section_type.replace("_", " ").title(),
                narrative=narrative,
                key_findings=key_findings,
                requires_review=section_hitl_needed
            ))

        # 3. Build Comparison Matrix Rows
        # Identify all unique coverage/field names across all quotes
        matrix_map = {} # (section, field) -> ProposalComparisonRow
        
        for doc_id, changes in all_changes.items():
            for c in changes:
                key = (c.section_type, c.canonical_coverage_name or c.coverage_name or c.field_name)
                if key not in matrix_map:
                    matrix_map[key] = ProposalComparisonRow(
                        category=c.section_type.title(),
                        label=key[1],
                        expiring_value=c.old_value,
                        renewal_values={},
                        is_canonical=c.canonical_coverage_name is not None
                    )
                # Add this renewal's value
                matrix_map[key].renewal_values[doc_id] = c.new_value
                # Update delta/flag (using primary or worst case)
                if c.delta_type in ["GAP", "NEGATIVE_CHANGE"]:
                    matrix_map[key].delta_type = c.delta_type
                    matrix_map[key].delta_flag = c.delta_flag

        comparison_rows = sorted(matrix_map.values(), key=lambda x: (x.category, x.label))

        # 4. Generate Executive Summary using all changes
        flat_changes = [c for changes in all_changes.values() for c in changes]
        executive_summary = await self.narrative_service.generate_executive_summary(flat_changes)

        # 5. Extract basic policy info
        insured_name = "Insured"
        carrier_name = "Various Carriers"
        policy_type = "Commercial Policy"
        
        for c in flat_changes:
            if c.field_name == "insured_name" and c.new_value:
                insured_name = str(c.new_value)
            if c.field_name == "policy_type" and c.new_value:
                policy_type = str(c.new_value)

        # 6. Build Premium Summary (Extract from changes)
        premium_summary = []
        for doc_id, doc_changes in all_changes.items():
            # Try to find specific premium fields
            p_premium = next((c.new_value for c in doc_changes if c.section_type == "premium" and "total" in c.field_name.lower()), "$XX,XXX")
            p_carrier = next((c.new_value for c in doc_changes if c.field_name == "carrier_name"), f"Carrier ({doc_id[:8]})")
            p_terms = next((c.new_value for c in doc_changes if "terms" in c.field_name.lower()), "Net 30")
            
            premium_summary.append(PremiumSummaryRow(
                carrier=str(p_carrier),
                total_premium=str(p_premium),
                terms=str(p_terms),
                binding_deadline="30 days"
            ))

        return Proposal(
            proposal_id=uuid4(),
            workflow_id=workflow_id,
            document_ids=document_ids,
            insured_name=insured_name,
            carrier_name=carrier_name,
            policy_type=policy_type,
            broker_name=metadata.get("broker_name", "FurtherAI Broker") if metadata else "FurtherAI Broker",
            executive_summary=executive_summary,
            sections=proposal_sections,
            comparison_table=comparison_rows,
            premium_summary=premium_summary,
            requires_hitl_review=len(global_hitl_items) > 0,
            hitl_items=global_hitl_items,
            metadata=metadata or {}
        )
