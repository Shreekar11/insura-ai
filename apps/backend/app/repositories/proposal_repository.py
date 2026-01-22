"""Repository for managing Proposal persistence."""

from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Proposal
from typing import Optional, List

class ProposalRepository:
    """Repository for Proposal database operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        workflow_id: UUID,
        insured_name: str,
        carrier_name: str,
        policy_type: str,
        proposal_json: dict,
        executive_summary: Optional[str] = None,
        pdf_path: Optional[str] = None,
    ) -> Proposal:
        """Create a new proposal record."""
        proposal = Proposal(
            workflow_id=workflow_id,
            insured_name=insured_name,
            carrier_name=carrier_name,
            policy_type=policy_type,
            proposal_json=proposal_json,
            executive_summary=executive_summary,
            pdf_path=pdf_path
        )
        self.session.add(proposal)
        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def get_by_workflow_id(self, workflow_id: UUID) -> List[Proposal]:
        """Get all proposals for a workflow."""
        stmt = select(Proposal).where(Proposal.workflow_id == workflow_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, proposal_id: UUID) -> Optional[Proposal]:
        """Get proposal by ID."""
        stmt = select(Proposal).where(Proposal.id == proposal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
        
    async def update_pdf_path(self, proposal_id: UUID, pdf_path: str) -> Optional[Proposal]:
        """Update the PDF path for a proposal."""
        proposal = await self.get_by_id(proposal_id)
        if proposal:
            proposal.pdf_path = pdf_path
            await self.session.commit()
            await self.session.refresh(proposal)
        return proposal
