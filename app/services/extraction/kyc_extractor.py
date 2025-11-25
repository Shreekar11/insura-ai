"""KYC (Know Your Customer) extraction service.

This service extracts KYC information from insurance documents.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import KYCItem
from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class KYCExtractor(BaseExtractor):
    """Extracts KYC information from documents.
    
    This service identifies and extracts structured KYC (Know Your Customer)
    information including customer details, identification, and verification data.
    
    Inherits from BaseExtractor for common LLM and parsing utilities.
    """
    
    KYC_EXTRACTION_PROMPT = """You are an expert at extracting KYC (Know Your Customer) information from insurance documents.

Analyze the following text and extract ALL KYC information.

**Each KYC record should include:**
- customer_name: Full legal name of customer/entity
- customer_type: Type (e.g., "Individual", "Corporation", "Partnership", "LLC")
- date_of_birth: Date of birth for individuals (YYYY-MM-DD format)
- incorporation_date: Date of incorporation for entities (YYYY-MM-DD format)
- tax_id: Tax identification number (SSN, EIN, etc.)
- business_type: Type of business (if applicable)
- industry: Industry sector
- address: Complete address
- city: City
- state: State/Province
- zip_code: ZIP/Postal code
- country: Country
- phone: Phone number
- email: Email address
- website: Website URL
- identification_type: Type of ID (e.g., "Driver's License", "Passport", "Articles of Incorporation")
- identification_number: ID number
- identification_issuer: Issuing authority
- identification_expiry: ID expiry date (YYYY-MM-DD format)
- authorized_signers: List of authorized signers/representatives
- ownership_structure: Ownership information (for entities)
- annual_revenue: Annual revenue (if disclosed)
- employee_count: Number of employees

**Return ONLY valid JSON** array (no code fences, no explanations):
[
  {
    "customer_name": "ABC Manufacturing LLC",
    "customer_type": "LLC",
    "date_of_birth": null,
    "incorporation_date": "2015-06-15",
    "tax_id": "12-3456789",
    "business_type": "Manufacturing",
    "industry": "Industrial Equipment",
    "address": "456 Industrial Parkway",
    "city": "Springfield",
    "state": "IL",
    "zip_code": "62701",
    "country": "USA",
    "phone": "+1-555-123-4567",
    "email": "contact@abcmfg.com",
    "website": "www.abcmfg.com",
    "identification_type": "Articles of Incorporation",
    "identification_number": "LLC-2015-12345",
    "identification_issuer": "Illinois Secretary of State",
    "identification_expiry": null,
    "authorized_signers": ["John Smith - CEO", "Jane Doe - CFO"],
    "ownership_structure": "Member-managed LLC with 3 members",
    "annual_revenue": 5000000,
    "employee_count": 50
  }
]

**Important:**
- Extract ALL KYC information from the document
- Use null for missing values
- Ensure dates are in YYYY-MM-DD format
- Ensure numeric values are numbers, not strings
- Protect sensitive information appropriately
- Include both individual and entity information
"""
    
    def get_extraction_prompt(self) -> str:
        """Get the LLM prompt for KYC extraction.
        
        Returns:
            str: System prompt for LLM
        """
        return self.KYC_EXTRACTION_PROMPT
    
    async def run(
        self,
        text: str,
        document_id: UUID,
        chunk_id: Optional[UUID] = None
    ) -> List[KYCItem]:
        """Extract KYC information from text.
        
        Args:
            text: Text to extract from
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            List[KYCItem]: Extracted KYC records
        """
        if not text or not text.strip():
            LOGGER.warning("Empty text provided for KYC extraction")
            return []
        
        LOGGER.info(
            "Starting KYC extraction",
            extra={"document_id": str(document_id), "text_length": len(text)}
        )
        
        try:
            # Call LLM for extraction (using base class method)
            kyc_data = await self._call_llm_api(text)
            
            # Create KYCItem records
            kyc_items = []
            for item_data in kyc_data:
                kyc_item = await self._create_kyc_item(
                    item_data=item_data,
                    document_id=document_id,
                    chunk_id=chunk_id
                )
                kyc_items.append(kyc_item)
            
            LOGGER.info(
                f"Extracted {len(kyc_items)} KYC records",
                extra={"document_id": str(document_id)}
            )
            
            return kyc_items
            
        except Exception as e:
            LOGGER.error(
                f"KYC extraction failed: {e}",
                exc_info=True,
                extra={"document_id": str(document_id)}
            )
            return []

    async def _create_kyc_item(
        self,
        item_data: Dict[str, Any],
        document_id: UUID,
        chunk_id: Optional[UUID]
    ) -> KYCItem:
        """Create KYCItem record.
        
        Args:
            item_data: Extracted item data
            document_id: Document ID
            chunk_id: Optional chunk ID
            
        Returns:
            KYCItem: Created database record
        """
        kyc_item = KYCItem(
            document_id=document_id,
            chunk_id=chunk_id,
            customer_name=item_data.get("customer_name"),
            customer_type=item_data.get("customer_type"),
            date_of_birth=self._parse_date(item_data.get("date_of_birth")),
            incorporation_date=self._parse_date(item_data.get("incorporation_date")),
            tax_id=item_data.get("tax_id"),
            business_type=item_data.get("business_type"),
            industry=item_data.get("industry"),
            address=item_data.get("address"),
            city=item_data.get("city"),
            state=item_data.get("state"),
            zip_code=item_data.get("zip_code"),
            country=item_data.get("country"),
            phone=item_data.get("phone"),
            email=item_data.get("email"),
            website=item_data.get("website"),
            identification_type=item_data.get("identification_type"),
            identification_number=item_data.get("identification_number"),
            identification_issuer=item_data.get("identification_issuer"),
            identification_expiry=self._parse_date(item_data.get("identification_expiry")),
            authorized_signers=item_data.get("authorized_signers"),
            ownership_structure=item_data.get("ownership_structure"),
            annual_revenue=self._to_decimal(item_data.get("annual_revenue")),
            employee_count=item_data.get("employee_count"),
            additional_data=item_data  # Store full data
        )
        
        self.session.add(kyc_item)
        await self.session.flush()
        
        return kyc_item
