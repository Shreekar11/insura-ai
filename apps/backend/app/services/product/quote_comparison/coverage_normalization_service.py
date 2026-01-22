"""Coverage Normalization Service for Quote Comparison workflow.

Maps carrier-specific coverage labels to canonical types and resolves
derived/percentage-based limits to absolute values.
"""

from uuid import UUID
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.product.quote_comparison import CanonicalCoverage, CoverageLimit
from app.schemas.product.extracted_data import CoverageFields, SECTION_DATA_MODELS
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Canonical coverage mapping - maps carrier-specific labels to canonical names
COVERAGE_CANONICAL_MAPPING: dict[str, str] = {
    # Property coverages
    "dwelling": "dwelling",
    "coverage a": "dwelling",
    "coverage a - dwelling": "dwelling",
    "building": "dwelling",
    "structure": "dwelling",
    
    "other structures": "other_structures",
    "coverage b": "other_structures",
    "coverage b - other structures": "other_structures",
    "detached structures": "other_structures",
    
    "personal property": "personal_property",
    "coverage c": "personal_property",
    "coverage c - personal property": "personal_property",
    "contents": "personal_property",
    
    "loss of use": "loss_of_use",
    "coverage d": "loss_of_use",
    "coverage d - loss of use": "loss_of_use",
    "additional living expense": "loss_of_use",
    
    "business income": "business_income",
    "business interruption": "business_income",
    
    # Liability coverages
    "personal liability": "personal_liability",
    "coverage e": "personal_liability",
    "coverage e - personal liability": "personal_liability",
    "bodily injury liability": "personal_liability",
    
    "medical payments": "medical_payments",
    "coverage f": "medical_payments",
    "coverage f - medical payments": "medical_payments",
    "medical payments to others": "medical_payments",
    
    "general liability": "general_liability",
    "commercial general liability": "general_liability",
    "cgl": "general_liability",
    
    # Add-on coverages
    "water backup": "water_backup",
    "sump overflow": "water_backup",
    
    "equipment breakdown": "equipment_breakdown",
    "mechanical breakdown": "equipment_breakdown",
    
    "identity theft": "identity_theft",
    "identity fraud": "identity_theft",
    
    "umbrella": "umbrella_liability",
    "excess liability": "umbrella_liability",
}

# Coverage category mapping
COVERAGE_CATEGORIES: dict[str, str] = {
    "dwelling": "property",
    "other_structures": "property",
    "personal_property": "property",
    "loss_of_use": "property",
    "business_income": "property",
    "personal_liability": "liability",
    "medical_payments": "liability",
    "general_liability": "liability",
    "umbrella_liability": "liability",
    "water_backup": "add_on",
    "equipment_breakdown": "add_on",
    "identity_theft": "add_on",
}

# Base coverages (vs optional)
BASE_COVERAGES: set[str] = {
    "dwelling",
    "other_structures",
    "personal_property",
    "loss_of_use",
    "personal_liability",
    "medical_payments",
    "general_liability",
}


class CoverageNormalizationService:
    """Service for normalizing extracted coverages to canonical schema."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = SectionExtractionRepository(session)
    
    async def normalize_coverages_for_document(
        self,
        document_id: UUID,
        workflow_id: UUID
    ) -> list[CanonicalCoverage]:
        """Normalize all coverages for a document.
        
        Args:
            document_id: The document to normalize coverages for
            workflow_id: Current workflow ID
            
        Returns:
            List of CanonicalCoverage objects
        """
        # Fetch coverage sections
        sections = await self.section_repo.get_document_by_section(
            document_id, "coverages"
        )
        
        canonical_coverages = []
        declarations_data = await self._get_declarations_data(document_id, workflow_id)
        
        for section in sections:
            extracted_fields = section.extracted_fields or {}
            
            # Handle both list and dict formats
            if isinstance(extracted_fields, list):
                for item in extracted_fields:
                    coverage = self._normalize_single_coverage(
                        item, document_id, declarations_data
                    )
                    if coverage:
                        canonical_coverages.append(coverage)
            elif isinstance(extracted_fields, dict):
                # Could be a single coverage or nested structure
                if "entities" in extracted_fields and isinstance(extracted_fields["entities"], list) and extracted_fields["entities"]:
                    for item in extracted_fields["entities"]:
                        coverage = self._normalize_single_coverage(
                            item, document_id, declarations_data
                        )
                        if coverage:
                            canonical_coverages.append(coverage)
                elif "coverages" in extracted_fields:
                    for item in extracted_fields["coverages"]:
                        coverage = self._normalize_single_coverage(
                            item, document_id, declarations_data
                        )
                        if coverage:
                            canonical_coverages.append(coverage)
                else:
                    coverage = self._normalize_single_coverage(
                        extracted_fields, document_id, declarations_data
                    )
                    if coverage:
                        canonical_coverages.append(coverage)
        
        return canonical_coverages
    
    async def _get_declarations_data(
        self,
        document_id: UUID,
        workflow_id: UUID
    ) -> Optional[dict]:
        """Fetch declarations section for resolving percentage limits."""
        sections = await self.section_repo.get_document_by_section(
            document_id, "declarations"
        )
        
        for section in sections:
            return section.extracted_fields
        
        return None
    
    def _normalize_single_coverage(
        self,
        raw_data: dict,
        document_id: UUID,
        declarations_data: Optional[dict] = None
    ) -> Optional[CanonicalCoverage]:
        """Normalize a single coverage item.
        
        Args:
            raw_data: Raw extracted coverage data
            document_id: Source document ID
            declarations_data: Declarations data for resolving percentages
            
        Returns:
            CanonicalCoverage or None if normalization fails
        """
        try:            
            # Extract attributes if nested in entity format
            attributes = raw_data.get("attributes", raw_data) if isinstance(raw_data, dict) else raw_data
            
            # Validate with CoverageFields schema
            coverage_schema = SECTION_DATA_MODELS.get("coverages", CoverageFields)
            validated = coverage_schema.model_validate(attributes)
            
            coverage_name = validated.coverage_name or ""
            canonical_name = self._map_to_canonical(coverage_name)
            
            if not canonical_name:
                LOGGER.warning(f"Could not map coverage '{coverage_name}' to canonical type")
                canonical_name = coverage_name.lower().replace(" ", "_")
            
            # Determine category
            category = None
            if validated.coverage_type:
                type_map = {
                    "property": "property",
                    "liability": "liability", 
                    "add-on": "add_on",
                    "addon": "add_on",
                    "add on": "add_on"
                }
                normalized_type = validated.coverage_type.lower().strip()
                category = type_map.get(normalized_type)
            
            if not category:
                category = COVERAGE_CATEGORIES.get(canonical_name, "add_on")
            
            # Normalize limit
            limit = self._normalize_limit(
                validated, declarations_data
            )
            
            # Determine if base coverage
            is_base = canonical_name in BASE_COVERAGES
            
            return CanonicalCoverage(
                canonical_coverage=canonical_name,
                original_label=coverage_name,
                category=category,  # type: ignore
                is_base=is_base,
                limit=limit,
                deductible=validated.deductible_amount,
                conditions=[],
                optional=not is_base,
                included=validated.is_included if validated.is_included is not None else True,
                confidence=Decimal("0.9"),  # Default confidence
                document_id=document_id
            )
            
        except Exception as e:
            LOGGER.error(f"Failed to normalize coverage: {e}", exc_info=True)
            return None
    
    def _map_to_canonical(self, coverage_name: str) -> Optional[str]:
        """Map carrier-specific coverage name to canonical type."""
        if not coverage_name:
            return None
        
        normalized = coverage_name.lower().strip()
        
        # Exact match
        if normalized in COVERAGE_CANONICAL_MAPPING:
            return COVERAGE_CANONICAL_MAPPING[normalized]
        
        # Partial match
        for key, canonical in COVERAGE_CANONICAL_MAPPING.items():
            if key in normalized or normalized in key:
                return canonical
        
        return None
    
    def _normalize_limit(
        self,
        coverage: CoverageFields,
        declarations_data: Optional[dict] = None
    ) -> CoverageLimit:
        """Normalize coverage limit, resolving percentages to absolute values."""
        
        # Try to get the limit amount
        limit_amount = (
            coverage.limit_amount or 
            coverage.limit_per_occurrence or 
            coverage.limit_aggregate
        )
        
        if limit_amount is not None:
            return CoverageLimit(
                type="absolute",
                value=limit_amount,
                derived_from=None
            )
        
        # If no direct limit, assume percentage based on coverage type
        # and try to derive from declarations (Coverage A)
        if declarations_data and coverage.coverage_name:
            dwelling_value = declarations_data.get("dwelling_limit") or declarations_data.get("coverage_a")
            if dwelling_value:
                # Common percentage derivations
                derivation_rules = {
                    "other_structures": Decimal("0.10"),
                    "personal_property": Decimal("0.50"),
                    "loss_of_use": Decimal("0.20"),
                }
                canonical = self._map_to_canonical(coverage.coverage_name)
                if canonical in derivation_rules:
                    derived_value = Decimal(str(dwelling_value)) * derivation_rules[canonical]
                    return CoverageLimit(
                        type="percentage",
                        value=derived_value,
                        derived_from="dwelling"
                    )
        
        # Default to zero if no limit found
        return CoverageLimit(
            type="absolute",
            value=Decimal("0"),
            derived_from=None
        )
