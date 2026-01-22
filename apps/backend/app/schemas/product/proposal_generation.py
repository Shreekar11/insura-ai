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

class ProposalComparisonRow(BaseModel):
    """A single row in a comparison table."""
    category: str
    label: str
    expiring_value: Any
    renewal_value: Any
    delta_type: str
    delta_flag: str
    is_canonical: bool = False

class Proposal(BaseModel):
    """Full insurance proposal model."""
    proposal_id: UUID
    workflow_id: UUID
    document_ids: List[UUID]
    
    insured_name: str
    carrier_name: str
    policy_type: str
    
    executive_summary: str
    sections: List[ProposalSection]
    comparison_table: List[ProposalComparisonRow]
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
