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
        changes: List[ComparisonChange],
        metadata: Dict[str, Any] = None
    ) -> Proposal:
        """Assemble a complete Proposal object."""
        
        # 1. Group changes by section
        section_groups = {}
        for c in changes:
            if c.section_type not in section_groups:
                section_groups[c.section_type] = []
            section_groups[c.section_type].append(c)

        # 2. Generate sections and narratives
        proposal_sections = []
        global_hitl_items = []
        
        for section_type, section_changes in section_groups.items():
            narrative = await self.narrative_service.generate_section_narrative(
                section_type, 
                section_changes
            )
            
            # Key findings (GAPs and ADVANTAGEs)
            key_findings = []
            section_hitl_needed = False
            section_hitl_reasons = []
            
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
                        reason = f"Coverage Gap: {c.coverage_name or c.field_name} removed"
                        section_hitl_reasons.append(reason)
                        global_hitl_items.append(reason)

            proposal_sections.append(ProposalSection(
                section_type=section_type,
                title=section_type.replace("_", " ").title(),
                narrative=narrative,
                key_findings=key_findings,
                requires_review=section_hitl_needed,
                review_reason="; ".join(section_hitl_reasons) if section_hitl_reasons else None
            ))

        # 3. Build Comparison Table Rows (Side-by-side)
        comparison_rows = []
        for c in changes:
            comparison_rows.append(ProposalComparisonRow(
                category=c.section_type.title(),
                label=c.canonical_coverage_name or c.coverage_name or c.field_name,
                expiring_value=c.old_value,
                renewal_value=c.new_value,
                delta_type=c.delta_type or "NEUTRAL",
                delta_flag=c.delta_flag or "NEUTRAL",
                is_canonical=c.canonical_coverage_name is not None,
                reasoning=c.reasoning
            ))

        # 4. Generate Executive Summary
        executive_summary = await self.narrative_service.generate_executive_summary(changes)

        # 5. Extract basic policy info from changes
        insured_name = "Insured"
        carrier_name = "Carrier"
        policy_type = "Commercial Policy"
        
        for c in changes:
            if c.field_name == "insured_name" and c.new_value:
                insured_name = str(c.new_value)
            if c.field_name == "carrier_name" and c.new_value:
                carrier_name = str(c.new_value)
            if c.field_name == "policy_type" and c.new_value:
                policy_type = str(c.new_value)

        # 6. Calculate quality score (0.0-1.0)
        # Simple heuristic: 1.0 base, -0.1 for each GAP, -0.05 for each NEGATIVE_CHANGE
        quality_score = 1.0
        gaps = sum(1 for c in changes if c.delta_type == "GAP")
        negatives = sum(1 for c in changes if c.delta_type == "NEGATIVE_CHANGE")
        quality_score = max(0.0, 1.0 - (gaps * 0.1) - (negatives * 0.05))

        return Proposal(
            proposal_id=uuid4(),
            workflow_id=workflow_id,
            document_ids=document_ids,
            insured_name=insured_name,
            carrier_name=carrier_name,
            policy_type=policy_type,
            executive_summary=executive_summary,
            sections=proposal_sections,
            comparison_table=comparison_rows,
            requires_hitl_review=len(global_hitl_items) > 0,
            hitl_items=global_hitl_items,
            quality_score=quality_score,
            metadata=metadata or {}
        )
