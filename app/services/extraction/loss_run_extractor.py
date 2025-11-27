"""Loss Run extraction service.

This service extracts structured loss run (claims history) data from
insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import LossRunClaim
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class LossRunExtractor(BaseExtractor):
    """Extracts Loss Run claim data from documents.
    
    This service identifies loss run documents and extracts structured
    claims history information.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    LOSS_RUN_EXTRACTION_PROMPT = """You are an expert at extracting Loss Run (claims history) data from insurance documents.

Analyze the following text and extract ALL loss run claim items.

**Each claim should include:**
- claim_number: Claim identification number
- policy_number: Associated policy number
- insured_name: Name of insured
- loss_date: Date of loss (YYYY-MM-DD format)
- report_date: Date claim was reported (YYYY-MM-DD format)
- cause_of_loss: Cause/type of loss (Fire, Water, Theft, etc.)
- description: Claim description
- incurred_amount: Total incurred amount
- paid_amount: Amount paid to date
- reserve_amount: Reserve amount
- status: Claim status (Open, Closed, etc.)

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "claim_number": "CLM-2023-001",
    "policy_number": "POL123456",
    "insured_name": "ABC Company",
    "loss_date": "2023-05-15",
    "report_date": "2023-05-16",
    "cause_of_loss": "Fire",
    "description": "Kitchen fire damage",
    "incurred_amount": 50000.00,
    "paid_amount": 45000.00,
    "reserve_amount": 5000.00,
    "status": "Open"
  }
]

**Important:**
- Extract ALL claims from tables/schedules
- Use null for missing values
- Ensure dates are in YYYY-MM-DD format
- Ensure numeric values are numbers, not strings
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for Loss Run extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.LOSS_RUN_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[LossRunClaim]:
        """Extract loss run claims from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[LossRunClaim]: Extracted claims
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for loss run extraction")
            return []
        
        LOGGER.info(
            "Starting loss run extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            claims_data = await self._call_llm_api(text)
            
            # Create LossRunClaim records
            claims = []
            for claim_data in claims_data:
                claim = await self._create_loss_run_claim(
                    claim_data=claim_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                claims.append(claim)
            
            LOGGER.info(
                f"Extracted {len(claims)} loss run claims",
                extra={"document_id": str(document_id)}
            )
            
            return claims
            
        except Exception as e:
            LOGGER.error(
                f"Loss run extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _create_loss_run_claim(
        self,
        claim_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> LossRunClaim:
        """Create LossRunClaim record.
        
        Args:
            claim_data: Extracted claim data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            LossRunClaim: Created database record
        """
        claim = LossRunClaim(
            document_id=document_id,
            chunk_id=chunk_id,
            claim_number=claim_data.get("claim_number"),
            policy_number=claim_data.get("policy_number"),
            insured_name=claim_data.get("insured_name"),
            loss_date=self._parse_date(claim_data.get("loss_date")),
            report_date=self._parse_date(claim_data.get("report_date")),
            cause_of_loss=claim_data.get("cause_of_loss"),
            description=claim_data.get("description"),
            incurred_amount=self._to_decimal(claim_data.get("incurred_amount")),
            paid_amount=self._to_decimal(claim_data.get("paid_amount")),
            reserve_amount=self._to_decimal(claim_data.get("reserve_amount")),
            status=claim_data.get("status"),
            additional_data=claim_data  # Store full data
        )
        
        self.session.add(claim)
        await self.session.flush()
        
        return claim
