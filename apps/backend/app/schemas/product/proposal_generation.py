"""Pydantic schemas for Proposal Generation."""

from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Dict, Any, Optional
from datetime import datetime

class ProposalSection(BaseModel):
    """A single section within a proposal."""
    section_type: str
    title: str
    narrative: str
    key_findings: List[Dict[str, Any]]
    raw_data: Optional[Dict[str, Any]] = None
    requires_review: bool = False
    review_reason: Optional[str] = None

class ProposalComparisonRow(BaseModel):
    """A single row in a comparison table with support for multiple quotes."""
    category: str
    label: str
    expiring_value: Any
    # Map of Carrier/DocID to Value
    renewal_values: Dict[str, Any] = Field(default_factory=dict)
    
    # For backwards compatibility or primary comparison
    delta_type: str = "NEUTRAL"
    delta_flag: str = "NEUTRAL"
    
    recommendation: Optional[str] = None
    is_canonical: bool = False
    reasoning: Optional[str] = None

class PremiumSummaryRow(BaseModel):
    """A row in the premium summary table."""
    carrier: str
    total_premium: str
    terms: str
    binding_deadline: str

class Proposal(BaseModel):
    """Full insurance proposal model."""
    proposal_id: UUID
    workflow_id: UUID
    document_ids: List[UUID]
    
    insured_name: str
    carrier_name: str
    policy_type: str
    
    # Branding
    broker_name: Optional[str] = "FurtherAI Broker"
    broker_logo_path: Optional[str] = None
    
    executive_summary: str
    sections: List[ProposalSection]
    comparison_table: List[ProposalComparisonRow]
    premium_summary: List[PremiumSummaryRow] = Field(default_factory=list)
    
    disclaimers: List[str] = Field(default_factory=lambda: [
        "Indications subject to UW approval.",
        "Contact your broker to bind."
    ])
    
    requires_hitl_review: bool = False
    hitl_items: List[str] = Field(default_factory=list)
    quality_score: Optional[float] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
