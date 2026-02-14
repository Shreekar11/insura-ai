"""Table validation service for validating extracted table data.

This service validates tables according to business rules:
- SOV: TIV totals, no negative values, missing addresses flagged
- Loss Run: Paid ≤ incurred, dates within policy term, claim numbers unique
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal

from app.database.models import SOVItem, LossRunClaim
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    
    issue_type: str
    severity: str  # error, warning, info
    message: str
    row_index: Optional[int] = None
    expected_value: Optional[Any] = None
    actual_value: Optional[Any] = None


@dataclass
class ValidationResult:
    """Table validation result."""
    
    passed: bool
    issues: List[ValidationIssue]
    summary: Dict[str, Any]


class TableValidationService:
    """Service for validating extracted table data.
    
    Performs business rule validation on SOV and Loss Run tables.
    """
    
    def __init__(self):
        """Initialize table validation service."""
        LOGGER.info("Initialized TableValidationService")
    
    def validate_sov_table(
        self,
        sov_items: List[SOVItem],
        declared_tiv: Optional[Decimal] = None
    ) -> ValidationResult:
        """Validate SOV table data.
        
        Args:
            sov_items: List of SOVItem objects
            declared_tiv: Optional declared total TIV for comparison
            
        Returns:
            ValidationResult with issues and summary
        """
        issues = []
        
        # Calculate total TIV
        total_tiv = sum(
            (item.total_insured_value or Decimal(0))
            for item in sov_items
            if item.total_insured_value is not None
        )
        
        # Check TIV match if declared TIV provided
        if declared_tiv is not None:
            if abs(total_tiv - declared_tiv) > Decimal("0.01"):  # Allow small rounding differences
                issues.append(ValidationIssue(
                    issue_type="tiv_mismatch",
                    severity="error",
                    message=f"Total TIV mismatch: expected {declared_tiv}, actual {total_tiv}",
                    expected_value=float(declared_tiv),
                    actual_value=float(total_tiv)
                ))
        
        # Check for negative values
        for idx, item in enumerate(sov_items):
            if item.building_limit is not None and item.building_limit < 0:
                issues.append(ValidationIssue(
                    issue_type="negative_value",
                    severity="error",
                    message=f"Negative building value: {item.building_limit}",
                    row_index=idx,
                    actual_value=float(item.building_limit)
                ))
            
            if item.contents_limit is not None and item.contents_limit < 0:
                issues.append(ValidationIssue(
                    issue_type="negative_value",
                    severity="error",
                    message=f"Negative contents value: {item.contents_limit}",
                    row_index=idx,
                    actual_value=float(item.contents_limit)
                ))
            
            if item.total_insured_value is not None and item.total_insured_value < 0:
                issues.append(ValidationIssue(
                    issue_type="negative_value",
                    severity="error",
                    message=f"Negative TIV: {item.total_insured_value}",
                    row_index=idx,
                    actual_value=float(item.total_insured_value)
                ))
        
        # Check for missing addresses
        for idx, item in enumerate(sov_items):
            if not item.address or item.address.strip() == "":
                issues.append(ValidationIssue(
                    issue_type="missing_address",
                    severity="warning",
                    message="Missing address",
                    row_index=idx
                ))
        
        # Check for duplicate locations
        location_numbers = {}
        for idx, item in enumerate(sov_items):
            if item.location_number:
                if item.location_number in location_numbers:
                    issues.append(ValidationIssue(
                        issue_type="duplicate_location",
                        severity="warning",
                        message=f"Duplicate location number: {item.location_number}",
                        row_index=idx
                    ))
                else:
                    location_numbers[item.location_number] = idx
        
        summary = {
            "total_locations": len(sov_items),
            "total_tiv": float(total_tiv),
            "declared_tiv": float(declared_tiv) if declared_tiv else None,
            "tiv_match": declared_tiv is None or abs(total_tiv - declared_tiv) <= Decimal("0.01"),
            "locations_with_addresses": sum(1 for item in sov_items if item.address),
            "unique_location_numbers": len(location_numbers),
            "error_count": sum(1 for issue in issues if issue.severity == "error"),
            "warning_count": sum(1 for issue in issues if issue.severity == "warning"),
        }
        
        passed = all(issue.severity != "error" for issue in issues)
        
        return ValidationResult(
            passed=passed,
            issues=issues,
            summary=summary
        )
    
    def validate_loss_run_table(
        self,
        claims: List[LossRunClaim],
        policy_start_date: Optional[datetime] = None,
        policy_end_date: Optional[datetime] = None
    ) -> ValidationResult:
        """Validate Loss Run table data.
        
        Args:
            claims: List of LossRunClaim objects
            policy_start_date: Optional policy start date
            policy_end_date: Optional policy end date
            
        Returns:
            ValidationResult with issues and summary
        """
        issues = []
        
        # Check paid ≤ incurred
        for idx, claim in enumerate(claims):
            if claim.paid_amount is not None and claim.incurred_amount is not None:
                if claim.paid_amount > claim.incurred_amount:
                    issues.append(ValidationIssue(
                        issue_type="paid_exceeds_incurred",
                        severity="error",
                        message=f"Paid amount ({claim.paid_amount}) exceeds incurred ({claim.incurred_amount})",
                        row_index=idx,
                        expected_value=float(claim.incurred_amount),
                        actual_value=float(claim.paid_amount)
                    ))
        
        # Check dates within policy term
        if policy_start_date and policy_end_date:
            for idx, claim in enumerate(claims):
                if claim.loss_date:
                    if claim.loss_date < policy_start_date.date():
                        issues.append(ValidationIssue(
                            issue_type="date_out_of_range",
                            severity="warning",
                            message=f"Loss date ({claim.loss_date}) before policy start ({policy_start_date.date()})",
                            row_index=idx,
                            actual_value=str(claim.loss_date)
                        ))
                    elif claim.loss_date > policy_end_date.date():
                        issues.append(ValidationIssue(
                            issue_type="date_out_of_range",
                            severity="warning",
                            message=f"Loss date ({claim.loss_date}) after policy end ({policy_end_date.date()})",
                            row_index=idx,
                            actual_value=str(claim.loss_date)
                        ))
        
        # Check for unique claim numbers
        claim_numbers = {}
        for idx, claim in enumerate(claims):
            if claim.claim_number:
                if claim.claim_number in claim_numbers:
                    issues.append(ValidationIssue(
                        issue_type="duplicate_claim_number",
                        severity="error",
                        message=f"Duplicate claim number: {claim.claim_number}",
                        row_index=idx
                    ))
                else:
                    claim_numbers[claim.claim_number] = idx
        
        # Calculate totals
        total_incurred = sum(
            (claim.incurred_amount or Decimal(0))
            for claim in claims
            if claim.incurred_amount is not None
        )
        total_paid = sum(
            (claim.paid_amount or Decimal(0))
            for claim in claims
            if claim.paid_amount is not None
        )
        total_reserve = sum(
            (claim.reserve_amount or Decimal(0))
            for claim in claims
            if claim.reserve_amount is not None
        )
        
        summary = {
            "total_claims": len(claims),
            "total_incurred": float(total_incurred),
            "total_paid": float(total_paid),
            "total_reserve": float(total_reserve),
            "unique_claim_numbers": len(claim_numbers),
            "open_claims": sum(1 for claim in claims if claim.status and "open" in claim.status.lower()),
            "closed_claims": sum(1 for claim in claims if claim.status and "closed" in claim.status.lower()),
            "error_count": sum(1 for issue in issues if issue.severity == "error"),
            "warning_count": sum(1 for issue in issues if issue.severity == "warning"),
        }
        
        passed = all(issue.severity != "error" for issue in issues)
        
        return ValidationResult(
            passed=passed,
            issues=issues,
            summary=summary
        )

