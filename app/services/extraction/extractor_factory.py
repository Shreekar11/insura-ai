"""Extractor factory for dynamic extractor selection and instantiation.

This module implements the Factory Pattern for scalable extraction routing.
It maintains a registry of extractors and dispatches to the appropriate
extractor based on section type.
"""

from typing import Dict, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.extraction.base_extractor import BaseExtractor
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class ExtractorFactory:
    """Factory for creating and managing extractors.
    
    This factory:
    - Maintains a registry mapping section types to extractor classes
    - Supports multiple aliases for the same extractor (e.g., "SOV", "Schedule of Values")
    - Dynamically instantiates extractors with dependency injection
    - Provides fallback to DefaultExtractor for unknown types
    
    Attributes:
        session: SQLAlchemy async session
        openrouter_api_key: OpenRouter API key
        openrouter_api_url: OpenRouter API URL
        openrouter_model: Model to use for extraction
        _registry: Mapping of normalized section types to extractor classes
        _instances: Cache of instantiated extractors
    """
    
    def __init__(
        self,
        session: AsyncSession,
        gemini_api_key: str,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: str = None, # Deprecated
        openrouter_api_url: str = None, # Deprecated
        openrouter_model: str = None, # Deprecated
    ):
        """Initialize extractor factory.
        
        Args:
            session: SQLAlchemy async session
            gemini_api_key: Gemini API key
            gemini_model: Model to use
        """
        self.session = session
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        
        # Registry mapping section types to extractor classes
        self._registry: Dict[str, Type[BaseExtractor]] = {}
        
        # Cache of instantiated extractors
        self._instances: Dict[str, BaseExtractor] = {}
        
        # Register default extractors
        self._register_default_extractors()
        
        LOGGER.info(
            "Initialized ExtractorFactory",
            extra={
                "registered_types": len(self._registry),
                "model": gemini_model
            }
        )
    
    def _register_default_extractors(self):
        """Register default extractors with their section type mappings.
        
        This method is called during initialization to set up the registry.
        Extractors are imported here to avoid circular dependencies.
        """
        # Import extractors here to avoid circular imports
        from app.services.extraction.sov_extractor import SOVExtractor
        from app.services.extraction.loss_run_extractor import LossRunExtractor
        from app.services.extraction.policy_extractor import PolicyExtractor
        from app.services.extraction.endorsement_extractor import EndorsementExtractor
        from app.services.extraction.invoice_extractor import InvoiceExtractor
        from app.services.extraction.conditions_extractor import ConditionsExtractor
        from app.services.extraction.coverages_extractor import CoveragesExtractor
        from app.services.extraction.exclusions_extractor import ExclusionsExtractor
        from app.services.extraction.claims_docs_extractor import ClaimsDocsExtractor
        from app.services.extraction.kyc_extractor import KYCExtractor
        from app.services.extraction.default_extractor import DefaultExtractor
        
        # Register SOV extractor with multiple aliases
        self.register_extractor(
            section_types=[
                "sov",
                "schedule of values",
                "statement of values",
                "schedule_of_values",
                "statement_of_values",
                "property schedule",
                "property_schedule",
            ],
            extractor_class=SOVExtractor
        )
        
        # Register Loss Run extractor with multiple aliases
        self.register_extractor(
            section_types=[
                "loss run",
                "loss_run",
                "loss runs",
                "loss_runs",
                "loss history",
                "loss_history",
                "claims history",
                "claims_history",
                "claim history",
                "claim_history",
            ],
            extractor_class=LossRunExtractor
        )
        
        # Register Policy extractor
        self.register_extractor(
            section_types=[
                "policy",
                "policy information",
                "policy_information",
                "policy details",
                "policy_details",
                "declarations",
                "declarations page",
                "declarations_page",
            ],
            extractor_class=PolicyExtractor
        )
        
        # Register Endorsement extractor
        self.register_extractor(
            section_types=[
                "endorsement",
                "endorsements",
                "amendment",
                "amendments",
                "policy change",
                "policy_change",
                "policy amendment",
                "policy_amendment",
            ],
            extractor_class=EndorsementExtractor
        )
        
        # Register Invoice extractor
        self.register_extractor(
            section_types=[
                "invoice",
                "invoices",
                "payment",
                "payments",
                "billing",
                "premium invoice",
                "premium_invoice",
                "payment schedule",
                "payment_schedule",
            ],
            extractor_class=InvoiceExtractor
        )
        
        # Register Conditions extractor
        self.register_extractor(
            section_types=[
                "conditions",
                "policy conditions",
                "policy_conditions",
                "general conditions",
                "general_conditions",
                "terms and conditions",
                "terms_and_conditions",
            ],
            extractor_class=ConditionsExtractor
        )
        
        # Register Coverages extractor
        self.register_extractor(
            section_types=[
                "coverages",
                "coverage",
                "insuring agreement",
                "insuring_agreement",
                "covered perils",
                "covered_perils",
                "what is covered",
                "what_is_covered",
            ],
            extractor_class=CoveragesExtractor
        )
        
        # Register Exclusions extractor
        self.register_extractor(
            section_types=[
                "exclusions",
                "exclusion",
                "what is not covered",
                "what_is_not_covered",
                "limitations",
                "policy exclusions",
                "policy_exclusions",
            ],
            extractor_class=ExclusionsExtractor
        )
        
        # Register Claims Docs extractor
        self.register_extractor(
            section_types=[
                "claims",
                "claim",
                "claims docs",
                "claims_docs",
                "claim documents",
                "claim_documents",
                "claim notice",
                "claim_notice",
                "loss notice",
                "loss_notice",
            ],
            extractor_class=ClaimsDocsExtractor
        )
        
        # Register KYC extractor
        self.register_extractor(
            section_types=[
                "kyc",
                "know your customer",
                "know_your_customer",
                "customer information",
                "customer_information",
                "insured information",
                "insured_information",
                "applicant information",
                "applicant_information",
            ],
            extractor_class=KYCExtractor
        )
        
        # Register default extractor as fallback
        self._default_extractor_class = DefaultExtractor
    
    
    def register_extractor(
        self,
        section_types: List[str],
        extractor_class: Type[BaseExtractor]
    ):
        """Register an extractor for multiple section types.
        
        Args:
            section_types: List of section type strings (will be normalized)
            extractor_class: Extractor class to instantiate
        """
        for section_type in section_types:
            normalized = self._normalize_section_type(section_type)
            self._registry[normalized] = extractor_class
            
        LOGGER.debug(
            f"Registered {extractor_class.__name__} for {len(section_types)} section types"
        )
    
    def get_extractor(self, section_type: str) -> BaseExtractor:
        """Get the appropriate extractor for a section type.
        
        This method:
        1. Normalizes the section type
        2. Looks up the extractor class in the registry
        3. Returns a cached instance or creates a new one
        4. Falls back to DefaultExtractor if type is unknown
        
        Args:
            section_type: Section type string from chunk metadata
            
        Returns:
            BaseExtractor: Instantiated extractor
        """
        if not section_type:
            return self._get_default_extractor()
        
        normalized = self._normalize_section_type(section_type)
        
        # Check if we have this extractor cached
        if normalized in self._instances:
            return self._instances[normalized]
        
        # Look up extractor class in registry
        extractor_class = self._registry.get(normalized)
        
        if not extractor_class:
            LOGGER.info(
                f"No extractor registered for section type '{section_type}', using default",
                extra={"section_type": section_type, "normalized": normalized}
            )
            return self._get_default_extractor()
        
        # Instantiate and cache the extractor
        extractor = extractor_class(
            session=self.session,
            gemini_api_key=self.gemini_api_key,
            gemini_model=self.gemini_model,
        )
        
        self._instances[normalized] = extractor
        
        LOGGER.debug(
            f"Instantiated {extractor_class.__name__} for section type '{section_type}'"
        )
        
        return extractor
    
    def _get_default_extractor(self) -> BaseExtractor:
        """Get the default extractor instance.
        
        Returns:
            BaseExtractor: Default extractor instance
        """
        if "default" not in self._instances:
            self._instances["default"] = self._default_extractor_class(
                session=self.session,
                gemini_api_key=self.gemini_api_key,
                gemini_model=self.gemini_model,
            )
        
        return self._instances["default"]
    
    def _normalize_section_type(self, section_type: str) -> str:
        """Normalize section type for consistent lookup.
        
        Normalization:
        - Convert to lowercase
        - Replace underscores with spaces
        - Strip whitespace
        
        Args:
            section_type: Raw section type string
            
        Returns:
            str: Normalized section type
        """
        return section_type.lower().replace("_", " ").strip()
    
    def list_supported_types(self) -> List[str]:
        """List all supported section types.
        
        Returns:
            List[str]: All registered section types
        """
        return sorted(self._registry.keys())
    
    def get_extractor_class_name(self, section_type: str) -> str:
        """Get the name of the extractor class for a section type.
        
        Useful for logging and debugging.
        
        Args:
            section_type: Section type string
            
        Returns:
            str: Extractor class name
        """
        normalized = self._normalize_section_type(section_type)
        extractor_class = self._registry.get(normalized)
        
        if extractor_class:
            return extractor_class.__name__
        else:
            return self._default_extractor_class.__name__
