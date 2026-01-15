"""Centralized Pydantic schemas for extracted insurance data entities.

These schemas align with the extraction prompts defined in system_prompts.py
to ensure type safety and consistent data handling across the pipeline.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal
from datetime import date


class ExtractedBaseModel(BaseModel):
    """Base model for all extracted entities with shared config."""
    model_config = ConfigDict(from_attributes=True, extra="allow")


class PolicyFields(ExtractedBaseModel):
    """Schema for Declarations/Policy fields."""
    policy_number: Optional[str] = None
    insured_name: Optional[str] = None
    insured_address: Optional[str] = None
    effective_date: Optional[Union[date, str]] = None
    expiration_date: Optional[Union[date, str]] = None
    carrier_name: Optional[str] = None
    broker_name: Optional[str] = None
    total_premium: Optional[Decimal] = None
    policy_type: Optional[str] = None
    quote_type: Optional[str] = None
    is_bill: Optional[bool] = None
    
    # Optional fields
    additional_insureds: Optional[List[str]] = None
    policy_form: Optional[str] = None
    retroactive_date: Optional[Union[date, str]] = None
    prior_acts_coverage: Optional[str] = None
    line_of_business: Optional[str] = None
    currency: Optional[str] = "USD"


class CoverageFields(ExtractedBaseModel):
    """Schema for Coverage fields."""
    coverage_name: str
    coverage_type: Optional[str] = None
    limit_amount: Optional[Decimal] = None
    deductible_amount: Optional[Decimal] = None
    premium_amount: Optional[Decimal] = None
    description: Optional[str] = None
    sub_limits: Optional[List[Dict[str, Any]]] = None
    limit_per_occurrence: Optional[Decimal] = None
    limit_aggregate: Optional[Decimal] = None
    valuation_basis: Optional[str] = None
    coverage_basis: Optional[str] = None
    coverage_form: Optional[str] = None
    is_included: Optional[bool] = True
    coverage_territory: Optional[str] = None
    retroactive_date: Optional[Union[date, str]] = None
    coverage_category: Optional[str] = None
    
    # Motor specific (optional)
    vehicle_registration_number: Optional[str] = None
    year_of_manufacture: Optional[int] = None
    insured_declared_value: Optional[Decimal] = None


class ConditionFields(ExtractedBaseModel):
    """Schema for Policy Conditions."""
    condition_type: Optional[str] = None
    title: str
    description: Optional[str] = None
    applies_to: Optional[str] = None
    requirements: Optional[List[str]] = None
    consequences: Optional[str] = None
    reference: Optional[str] = None
    compliance_required: Optional[bool] = None


class ExclusionFields(ExtractedBaseModel):
    """Schema for Policy Exclusions."""
    exclusion_type: Optional[str] = None
    title: str
    description: Optional[str] = None
    applies_to: Optional[str] = None
    exceptions: Optional[str] = None
    reference: Optional[str] = None
    exclusion_scope: Optional[str] = None
    impacted_coverage: Optional[str] = None
    severity: Optional[str] = None


class EndorsementFields(ExtractedBaseModel):
    """Schema for Endorsements."""
    endorsement_name: str
    endorsement_number: Optional[str] = None
    endorsement_type: Optional[str] = None
    impacted_coverage: Optional[str] = None
    materiality: Optional[str] = None
    effective_date: Optional[Union[date, str]] = None


class DeductibleFields(ExtractedBaseModel):
    """Schema for Deductibles."""
    deductible_name: str
    amount: Optional[Decimal] = None
    percentage: Optional[Decimal] = None
    deductible_type: Optional[str] = None
    applies_to: Optional[str] = None
    applies_to_coverage: Optional[str] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    is_sir: Optional[bool] = False
    retention_type: Optional[str] = None


class PremiumFields(ExtractedBaseModel):
    """Schema for Premium and Billing."""
    total_premium: Optional[Decimal] = None
    premium_breakdown: Optional[List[Dict[str, Any]]] = None
    taxes_and_fees: Optional[List[Dict[str, Any]]] = None
    payment_terms: Optional[str] = None
    installment_schedule: Optional[List[Dict[str, Any]]] = None
    minimum_earned_premium: Optional[Decimal] = None
    term_length: Optional[str] = None


class InsuringAgreementFields(ExtractedBaseModel):
    """Schema for Insuring Agreement."""
    agreement_text: str
    covered_causes: Optional[List[str]] = None
    coverage_trigger: Optional[str] = None
    key_definitions: Optional[List[str]] = None
    coverage_basis: Optional[str] = None


# Generic map for section results
SECTION_DATA_MODELS = {
    "declarations": PolicyFields,
    "coverages": CoverageFields,
    "conditions": ConditionFields,
    "exclusions": ExclusionFields,
    "endorsements": EndorsementFields,
    "deductibles": DeductibleFields,
    "premium": PremiumFields,
    "insuring_agreement": InsuringAgreementFields,
}
