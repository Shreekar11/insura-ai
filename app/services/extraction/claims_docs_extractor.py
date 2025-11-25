"""Claims documents extraction service.

This service extracts claim-related information from insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ClaimItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ClaimsDocsExtractor(BaseExtractor):
    """Extracts claims information from documents.
    
    This service identifies and extracts structured information about
    insurance claims from claim documents, notices, and correspondence.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    CLAIMS_EXTRACTION_PROMPT = """You are an expert at extracting claims information from insurance documents.

Analyze the following text and extract ALL claims information.

**Each claim should include:**
- claim_number: Claim identification number
- policy_number: Associated policy number
- claimant_name: Name of claimant
- loss_date: Date of loss/incident (YYYY-MM-DD format)
- report_date: Date claim was reported (YYYY-MM-DD format)
- claim_type: Type of claim (e.g., "Property Damage", "Bodily Injury", "Theft")
- loss_description: Description of the loss or incident
- loss_location: Location where loss occurred
- claim_amount: Claimed amount
- paid_amount: Amount paid (if any)
- reserve_amount: Reserve amount set aside
- claim_status: Status (e.g., "Open", "Closed", "Pending", "Denied")
- adjuster_name: Name of claims adjuster
- denial_reason: Reason for denial (if applicable)

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "claim_number": "CLM-2024-001234",
    "policy_number": "POL-2023-5678",
    "claimant_name": "John Doe",
    "loss_date": "2024-03-15",
    "report_date": "2024-03-16",
    "claim_type": "Property Damage - Fire",
    "loss_description": "Fire damage to commercial building caused by electrical fault",
    "loss_location": "123 Main Street, City, State",
    "claim_amount": 250000.00,
    "paid_amount": 200000.00,
    "reserve_amount": 50000.00,
    "claim_status": "Open",
    "adjuster_name": "Jane Smith",
    "denial_reason": null
  }
]

**Important:**
- Extract ALL claims from the document
- Use null for missing values
- Ensure dates are in YYYY-MM-DD format
- Ensure numeric values are numbers, not strings
- Include partial information even if complete details aren't available
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for claims extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.CLAIMS_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[ClaimItem]:
        """Extract claims from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[ClaimItem]: Extracted claim records
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for claims extraction")
            return []
        
        LOGGER.info(
            "Starting claims extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            claims_data = await self._call_llm_api(text)
            
            # Create ClaimItem records
            claims = []
            for claim_data in claims_data:
                claim = await self._create_claim_item(
                    claim_data=claim_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                claims.append(claim)
            
            LOGGER.info(
                f"Extracted {len(claims)} claims",
                extra={"document_id": str(document_id)}
            )
            
            return claims
            
        except Exception as e:
            LOGGER.error(
                f"Claims extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _create_claim_item(
        self,
        claim_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> ClaimItem:
        """Create ClaimItem record.
        
        Args:
            claim_data: Extracted claim data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            ClaimItem: Created database record
        """
        claim = ClaimItem(
            document_id=document_id,
            chunk_id=chunk_id,
            claim_number=claim_data.get("claim_number"),
            policy_number=claim_data.get("policy_number"),
            claimant_name=claim_data.get("claimant_name"),
            loss_date=self._parse_date(claim_data.get("loss_date")),
            report_date=self._parse_date(claim_data.get("report_date")),
            claim_type=claim_data.get("claim_type"),
            loss_description=claim_data.get("loss_description"),
            loss_location=claim_data.get("loss_location"),
            claim_amount=self._to_decimal(claim_data.get("claim_amount")),
            paid_amount=self._to_decimal(claim_data.get("paid_amount")),
            reserve_amount=self._to_decimal(claim_data.get("reserve_amount")),
            claim_status=claim_data.get("claim_status"),
            adjuster_name=claim_data.get("adjuster_name"),
            denial_reason=claim_data.get("denial_reason"),
            additional_data=claim_data  # Store full data
        )
        
        self.session.add(claim)
        await self.session.flush()
        
        return claim
