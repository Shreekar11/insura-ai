"""Policy extraction service.

This service extracts structured policy information from insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PolicyItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class PolicyExtractor(BaseExtractor):
    """Extracts policy information from documents.
    
    This service identifies policy documents and extracts structured
    policy information including coverage details, premiums, and dates.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    POLICY_EXTRACTION_PROMPT = """You are an expert at extracting policy information from insurance documents.

Analyze the following text and extract ALL policy information.

**Each policy should include:**
- policy_number: Policy identification number
- policy_type: Type of policy (Property, Auto, General Liability, Workers Comp, etc.)
- insured_name: Name of insured party
- effective_date: Policy effective date (YYYY-MM-DD format)
- expiration_date: Policy expiration date (YYYY-MM-DD format)
- premium_amount: Total premium amount
- coverage_limits: JSON object with coverage limits by type (e.g., {"building": 1000000, "liability": 2000000})
- deductibles: JSON object with deductibles by coverage type (e.g., {"building": 5000, "liability": 10000})
- carrier_name: Insurance carrier/company name
- agent_name: Agent or broker name

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "policy_number": "POL-2024-001",
    "policy_type": "Commercial Property",
    "insured_name": "ABC Company LLC",
    "effective_date": "2024-01-01",
    "expiration_date": "2025-01-01",
    "premium_amount": 15000.00,
    "coverage_limits": {
      "building": 5000000,
      "contents": 1000000,
      "business_interruption": 500000
    },
    "deductibles": {
      "building": 5000,
      "contents": 2500
    },
    "carrier_name": "ABC Insurance Company",
    "agent_name": "John Smith"
  }
]

**Important:**
- Extract ALL policies from the document
- Use null for missing values
- Ensure dates are in YYYY-MM-DD format
- Ensure numeric values are numbers, not strings
- coverage_limits and deductibles should be JSON objects
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for policy extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.POLICY_EXTRACTION_PROMPT
    
    async def extract(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[PolicyItem]:
        """Extract policy items from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[PolicyItem]: Extracted policy items
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for policy extraction")
            return []
        
        LOGGER.info(
            "Starting policy extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            policy_data = await self._call_llm_api(text)
            
            # Create PolicyItem records
            policy_items = []
            for item_data in policy_data:
                policy_item = await self._create_policy_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                policy_items.append(policy_item)
            
            LOGGER.info(
                f"Extracted {len(policy_items)} policy items",
                extra={"document_id": str(document_id)}
            )
            
            return policy_items
            
        except Exception as e:
            LOGGER.error(
                f"Policy extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _create_policy_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> PolicyItem:
        """Create PolicyItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            PolicyItem: Created database record
        """
        policy_item = PolicyItem(
            document_id=document_id,
            chunk_id=chunk_id,
            policy_number=item_data.get("policy_number"),
            policy_type=item_data.get("policy_type"),
            insured_name=item_data.get("insured_name"),
            effective_date=self._parse_date(item_data.get("effective_date")),
            expiration_date=self._parse_date(item_data.get("expiration_date")),
            premium_amount=self._to_decimal(item_data.get("premium_amount")),
            coverage_limits=item_data.get("coverage_limits"),
            deductibles=item_data.get("deductibles"),
            carrier_name=item_data.get("carrier_name"),
            agent_name=item_data.get("agent_name"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(policy_item)
        await self.session.flush()
        
        return policy_item
