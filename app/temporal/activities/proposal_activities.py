"""Temporal activities for proposal generation."""

import os
from uuid import UUID
from typing import Dict, Any, List
from temporalio import activity

from app.core.database import get_db
from app.services.product.proposal_generation.assembly_service import ProposalAssemblyService
from app.services.product.proposal_generation.pdf_service import PDFProposalService
from app.services.product.proposal_generation.narrative_service import ProposalNarrativeService
from app.repositories.proposal_repository import ProposalRepository
from app.schemas.product.proposal import Proposal
from app.core.config import settings

# Mock or real storage service
from app.services.shared.storage_service import StorageService

@activity.defn
async def assemble_proposal_activity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble proposal data and generate narratives using LLM."""
    async for db in get_db():
        # Setup Services
        from app.core.unified_llm import create_llm_client_from_settings
        
        provider = payload.get("provider", settings.llm_provider)
        llm_client = create_llm_client_from_settings(
            provider=provider,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_model,
            openrouter_api_key=settings.openrouter_api_key,
            openrouter_api_url=settings.openrouter_api_url,
            openrouter_model=settings.openrouter_model
        )
        
        narrative_service = ProposalNarrativeService(client=llm_client)
        assembly_service = ProposalAssemblyService(narrative_service=narrative_service)
        
        workflow_id = UUID(payload["workflow_id"]) if isinstance(payload["workflow_id"], str) else payload["workflow_id"]
        document_ids = [UUID(d) if isinstance(d, str) else d for d in payload["document_ids"]]
        
        # 2. Get Changes (fetch if not provided)
        changes_data = payload.get("changes")
        from app.schemas.product.policy_comparison import ComparisonChange
        changes = [ComparisonChange(**c) for c in changes_data] if changes_data else []
        
        if not changes:
            # If no changes provided, we should ideally fetch from StepSectionOutputRepository
            # For now, we assume they are passed or handled by workflow
            LOGGER.warning(f"No changes provided for proposal assembly: {workflow_id}")

        # 3. Assemble
        proposal = await assembly_service.assemble_proposal(
            workflow_id=workflow_id,
            document_ids=document_ids,
            changes=changes
        )
        return proposal.model_dump()

@activity.defn
async def generate_pdf_activity(proposal_data: Dict[str, Any]) -> str:
    """Generate PDF and upload to storage."""
    proposal = Proposal(**proposal_data)
    pdf_service = PDFProposalService()
    
    pdf_buffer = pdf_service.generate_pdf(proposal)
    
    # Upload to storage
    storage_service = StorageService()
    bucket = "proposals"
    path = f"{proposal.proposal_id}.pdf"
    
    await storage_service.upload_file(
        pdf_buffer, 
        bucket=bucket,
        path=path,
        content_type="application/pdf"
    )
    
    return f"{bucket}/{path}"

@activity.defn
async def persist_proposal_activity(proposal_data: Dict[str, Any], pdf_path: str) -> Dict[str, Any]:
    """Persist proposal record to database."""
    async for db in get_db():
        repo = ProposalRepository(db)
        
        proposal = Proposal(**proposal_data)
        
        record = await repo.create(
            workflow_id=proposal.workflow_id,
            insured_name=proposal.insured_name,
            carrier_name=proposal.carrier_name,
            policy_type=proposal.policy_type,
            proposal_json=proposal.model_dump(),
            executive_summary=proposal.executive_summary,
            pdf_path=pdf_path
        )
        
        return {
            "id": str(record.id),
            "insured_name": record.insured_name,
            "pdf_path": record.pdf_path
        }
