"""Temporal activities for Proposal Generation workflow."""

import os
from uuid import UUID
from typing import Dict, Any, List
from temporalio import activity

from app.core.database import async_session_maker
from app.services.product.proposal_generation.proposal_comparison_service import ProposalComparisonService
from app.utils.logging import get_logger

from app.services.product.proposal_generation.assembly_service import ProposalAssemblyService
from app.services.product.proposal_generation.pdf_service import PDFProposalService
from app.services.product.proposal_generation.narrative_service import ProposalNarrativeService
from app.repositories.proposal_repository import ProposalRepository
from app.schemas.product.proposal import Proposal
from app.core.config import settings

# Mock or real storage service
from app.services.shared.storage_service import StorageService

LOGGER = get_logger(__name__)


@activity.defn
async def detect_document_roles_activity(
    workflow_id: str,
    document_ids: List[str],
) -> Dict[str, str]:
    """Detect which document is expiring vs. renewal.
    
    Args:
        workflow_id: Workflow ID
        document_ids: List of document IDs
        
    Returns:
        Dict with 'expiring' and 'renewal' document IDs
    """
    async with async_session_maker() as session:
        service = ProposalComparisonService(session)
        
        uuid_doc_ids = [UUID(d) if isinstance(d, str) else d for d in document_ids]
        uuid_workflow_id = UUID(workflow_id) if isinstance(workflow_id, str) else workflow_id
        
        roles = await service.detect_document_roles(
            workflow_id=uuid_workflow_id,
            document_ids=uuid_doc_ids,
        )
        
        return {
            "expiring": str(roles["expiring"]),
            "renewal": str(roles["renewal"]),
        }


@activity.defn
async def compare_documents_for_proposal_activity(
    workflow_id: str,
    expiring_doc_id: str,
    renewal_doc_id: str,
) -> List[Dict[str, Any]]:
    """Compare two documents for proposal generation.
    
    Args:
        workflow_id: Workflow ID
        expiring_doc_id: Expiring document ID
        renewal_doc_id: Renewal document ID
        
    Returns:
        List of comparison changes as dicts
    """
    async with async_session_maker() as session:
        service = ProposalComparisonService(session)
        
        changes = await service.compare_for_proposal(
            workflow_id=UUID(workflow_id),
            expiring_doc_id=UUID(expiring_doc_id),
            renewal_doc_id=UUID(renewal_doc_id),
        )
        
        # Convert to dicts for Temporal serialization
        return [change.model_dump() for change in changes]


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
