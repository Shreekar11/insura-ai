"""Invoice extraction service.

This service extracts structured invoice and payment information from
insurance billing documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import InvoiceItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class InvoiceExtractor(BaseExtractor):
    """Extracts invoice and payment information from documents.
    
    This service identifies invoices and extracts structured
    billing and payment information.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    INVOICE_EXTRACTION_PROMPT = """You are an expert at extracting invoice and payment information from insurance billing documents.

Analyze the following text and extract ALL invoice information.

**Each invoice should include:**
- invoice_number: Invoice identifier
- policy_number: Associated policy number
- invoice_date: Invoice date (YYYY-MM-DD format)
- due_date: Payment due date (YYYY-MM-DD format)
- total_amount: Total invoice amount
- amount_paid: Amount paid to date
- balance_due: Remaining balance
- payment_status: Status (Paid, Pending, Overdue, Partial, etc.)
- payment_method: Payment method if paid (Check, Credit Card, ACH, Wire, etc.)

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "invoice_number": "INV-2024-001",
    "policy_number": "POL-2024-001",
    "invoice_date": "2024-01-01",
    "due_date": "2024-01-31",
    "total_amount": 15000.00,
    "amount_paid": 15000.00,
    "balance_due": 0.00,
    "payment_status": "Paid",
    "payment_method": "ACH"
  }
]

**Important:**
- Extract ALL invoices from the document
- Use null for missing values
- Ensure dates are in YYYY-MM-DD format
- Ensure numeric values are numbers, not strings
- balance_due should equal total_amount minus amount_paid
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for invoice extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.INVOICE_EXTRACTION_PROMPT
    
    async def extract(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[InvoiceItem]:
        """Extract invoice items from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[InvoiceItem]: Extracted invoice items
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for invoice extraction")
            return []
        
        LOGGER.info(
            "Starting invoice extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            invoice_data = await self._call_llm_api(text)
            
            # Create InvoiceItem records
            invoice_items = []
            for item_data in invoice_data:
                invoice_item = await self._create_invoice_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                invoice_items.append(invoice_item)
            
            LOGGER.info(
                f"Extracted {len(invoice_items)} invoice items",
                extra={"document_id": str(document_id)}
            )
            
            return invoice_items
            
        except Exception as e:
            LOGGER.error(
                f"Invoice extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []
    
    async def _create_invoice_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> InvoiceItem:
        """Create InvoiceItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            InvoiceItem: Created database record
        """
        invoice_item = InvoiceItem(
            document_id=document_id,
            chunk_id=chunk_id,
            invoice_number=item_data.get("invoice_number"),
            policy_number=item_data.get("policy_number"),
            invoice_date=self._parse_date(item_data.get("invoice_date")),
            due_date=self._parse_date(item_data.get("due_date")),
            total_amount=self._to_decimal(item_data.get("total_amount")),
            amount_paid=self._to_decimal(item_data.get("amount_paid")),
            balance_due=self._to_decimal(item_data.get("balance_due")),
            payment_status=item_data.get("payment_status"),
            payment_method=item_data.get("payment_method"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(invoice_item)
        await self.session.flush()
        
        return invoice_item
