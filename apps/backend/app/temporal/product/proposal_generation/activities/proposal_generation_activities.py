"""Temporal activities for Proposal Generation workflow."""

import os
from uuid import UUID
from typing import Dict, Any, List
from temporalio import activity
from app.temporal.core.activity_registry import ActivityRegistry

from app.core.database import async_session_maker
from app.services.product.proposal_generation.proposal_comparison_service import ProposalComparisonService
from app.utils.logging import get_logger

from app.services.product.proposal_generation.assembly_service import ProposalAssemblyService

from app.services.product.proposal_generation.narrative_service import ProposalNarrativeService
from app.repositories.proposal_repository import ProposalRepository
from app.repositories.workflow_output_repository import WorkflowOutputRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.product.proposal_generation import Proposal
from app.core.config import settings

# Mock or real storage service
from app.services.storage_service import StorageService


LOGGER = get_logger(__name__)


@ActivityRegistry.register("proposal_generation", "normalize_coverages_for_proposal_activity")
@activity.defn
async def normalize_coverages_for_proposal_activity(
    workflow_id: str,
    expiring_doc_id: str,
    renewal_doc_ids: List[str],
) -> Dict[str, Any]:
    """Normalize coverage data across expiring and all renewal documents."""
    async with async_session_maker() as session:
        service = ProposalComparisonService(session) 
        expiring_raw = await service._fetch_and_normalize_data(
            UUID(expiring_doc_id), UUID(workflow_id), "coverages"
        )
        
        renewals_normalized = {}
        for rid in renewal_doc_ids:
            renewals_normalized[rid] = await service._fetch_and_normalize_data(
                UUID(rid), UUID(workflow_id), "coverages"
            )
            
        return {
            "expiring_normalized": expiring_raw,
            "renewals_normalized": renewals_normalized,
            "status": "completed"
        }


@ActivityRegistry.register("proposal_generation", "detect_document_roles_activity")
@activity.defn
async def detect_document_roles_activity(
    workflow_id: str,
    document_ids: List[str],
) -> Dict[str, Any]:
    """Detect which document is expiring vs. renewal(s)."""
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
            "renewals": [str(r) for r in roles["renewals"]],
        }


@ActivityRegistry.register("proposal_generation", "compare_documents_for_proposal_activity")
@activity.defn
async def compare_documents_for_proposal_activity(
    workflow_id: str,
    expiring_doc_id: str,
    renewal_doc_ids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Compare expiring document against multiple renewals."""
    async with async_session_maker() as session:
        service = ProposalComparisonService(session)
        output_repo = WorkflowOutputRepository(session)
        doc_repo = DocumentRepository(session)
        
        expiring_doc = await doc_repo.get_by_id(UUID(expiring_doc_id))
        expiring_name = expiring_doc.document_name if expiring_doc else "Expiring Policy"
        
        all_changes = {}
        
        for renewal_doc_id in renewal_doc_ids:
            renewal_doc = await doc_repo.get_by_id(UUID(renewal_doc_id))
            renewal_name = renewal_doc.document_name if renewal_doc else "Renewal Quote"

            # 1. Field-level comparison
            changes = await service.compare_for_proposal(
                workflow_id=UUID(workflow_id),
                expiring_doc_id=UUID(expiring_doc_id),
                renewal_doc_id=UUID(renewal_doc_id),
            )
            
            # 2. Entity-level comparison (for frontend display - usually only primary if multiple)
            # For now we only keep the last one or we could aggregate differently
            entity_comparison_result = await service.execute_entity_comparison(
                workflow_id=UUID(workflow_id),
                expiring_doc_id=UUID(expiring_doc_id),
                renewal_doc_id=UUID(renewal_doc_id),
                expiring_doc_name=expiring_name,
                renewal_doc_name=renewal_name
            )
            
            await output_repo.update_entity_comparison(
                workflow_id=UUID(workflow_id),
                entity_comparison=entity_comparison_result.model_dump(mode="json"),
            )
            
            all_changes[renewal_doc_id] = [change.model_dump() for change in changes]
        
        await session.commit()
        return all_changes


@ActivityRegistry.register("proposal_generation", "assemble_proposal_activity")
@activity.defn
async def assemble_proposal_activity(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble proposal data and generate narratives using LLM."""
    async with async_session_maker() as session:
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
        # payload["changes"] is now expected to be Dict[str, List[Dict[str, Any]]]
        all_changes_raw = payload.get("changes", {})
        from app.schemas.product.policy_comparison import ComparisonChange
        
        all_changes = {}
        if isinstance(all_changes_raw, dict):
            for doc_id, changes_list in all_changes_raw.items():
                all_changes[doc_id] = [ComparisonChange(**c) for c in changes_list]
        
        if not all_changes:
            LOGGER.warning(f"No changes provided for proposal assembly: {workflow_id}")

        # 3. Assemble
        proposal = await assembly_service.assemble_proposal(
            workflow_id=workflow_id,
            document_ids=document_ids,
            all_changes=all_changes
        )
        return proposal.model_dump()


@ActivityRegistry.register("proposal_generation", "generate_pdf_activity")
@activity.defn
async def generate_pdf_activity(proposal_data: Dict[str, Any]) -> str:
    """Generate PDF and upload to storage."""
    proposal = Proposal(**proposal_data)
    from app.services.product.proposal_generation.pdf_service import PDFProposalService
    pdf_service = PDFProposalService()
    
    pdf_buffer = pdf_service.generate_pdf(proposal)
    
    # Upload to storage
    storage_service = StorageService()
    bucket = "docs"
    path = f"{proposal.proposal_id}.pdf"
    
    await storage_service.upload_file(
        pdf_buffer, 
        bucket=bucket,
        path=path,
        content_type="application/pdf"
    )
    
    return f"{bucket}/{path}"


@ActivityRegistry.register("proposal_generation", "persist_proposal_activity")
@activity.defn
async def persist_proposal_activity(proposal_data: Dict[str, Any], pdf_path: str) -> Dict[str, Any]:
    """Persist proposal record to database."""
    async with async_session_maker() as session:
        repo = ProposalRepository(session)
        
        proposal = Proposal(**proposal_data)
        
        record = await repo.create(
            workflow_id=proposal.workflow_id,
            insured_name=proposal.insured_name,
            carrier_name=proposal.carrier_name,
            policy_type=proposal.policy_type,
            proposal_json=proposal.model_dump(mode="json"),
            executive_summary=proposal.executive_summary,
            pdf_path=pdf_path
        )
        
        return {
            "id": str(record.id),
            "insured_name": record.insured_name,
            "pdf_path": record.pdf_path
        }


@ActivityRegistry.register("proposal_generation", "validate_proposal_quality_activity")
@activity.defn
async def validate_proposal_quality_activity(proposal_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate proposal completeness and quality before PDF generation."""
    proposal = Proposal(**proposal_data)
    
    validation_errors = []
    
    # Check 1: Executive Summary presence
    if not proposal.executive_summary or len(proposal.executive_summary.strip()) < 50:
        validation_errors.append("Executive summary is missing or too short")
        
    # Check 2: Sections presence
    if not proposal.sections:
        validation_errors.append("No sections found in the proposal")
        
    # Check 3: At least one key finding if matches are partial/added/removed
    if not proposal.comparison_table:
        validation_errors.append("Comparison table is empty")
        
    # Check 4: Professional formatting checks (e.g. no placeholder text)
    placeholders = ["[placeholder]", "{placeholder}", "TBD", "INSERT NAME"]
    for p in placeholders:
        if p.lower() in proposal.executive_summary.lower():
            validation_errors.append(f"Found placeholder text in executive summary: {p}")
            break
            
    is_valid = len(validation_errors) == 0
    
    return {
        "validation_passed": is_valid,
        "errors": validation_errors,
        "quality_score": proposal.quality_score or 0.0
    }


