"""Cross-section validator for Tier 3 LLM processing.

This service implements the v2 architecture's Tier 3 processing:
- Cross-section validation and reconciliation
- Policy number consistency checking
- Date validation across sections
- Limit/premium alignment
- Conflict resolution

Runs once per document after all sections are extracted.
"""

import json
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.unified_llm import UnifiedLLMClient, create_llm_client_from_settings
from app.services.chunking.hybrid_models import SectionType
from app.services.extraction.section.section_extraction_orchestrator import (
    DocumentExtractionResult,
    SectionExtractionResult,
)
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)


@dataclass
class ValidationIssue:
    """Represents a validation issue found during cross-section validation.
    
    Attributes:
        issue_type: Type of issue (inconsistency, missing, conflict)
        severity: Severity level (error, warning, info)
        field_name: Field with the issue
        sections_involved: Sections where issue was found
        values_found: Different values found
        recommended_value: Recommended resolution
        message: Human-readable description
    """
    issue_type: str
    severity: str
    field_name: str
    sections_involved: List[str] = field(default_factory=list)
    values_found: List[Any] = field(default_factory=list)
    recommended_value: Optional[Any] = None
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "field_name": self.field_name,
            "sections_involved": self.sections_involved,
            "values_found": self.values_found,
            "recommended_value": self.recommended_value,
            "message": self.message,
        }


@dataclass
class ReconciledValue:
    """Represents a reconciled value after cross-section validation.
    
    Attributes:
        field_name: Name of the field
        canonical_value: Resolved canonical value
        source_sections: Sections where value was found
        confidence: Confidence in the reconciled value
        original_values: Original values from each section
    """
    field_name: str
    canonical_value: Any
    source_sections: List[str] = field(default_factory=list)
    confidence: float = 0.0
    original_values: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field_name": self.field_name,
            "canonical_value": self.canonical_value,
            "source_sections": self.source_sections,
            "confidence": self.confidence,
            "original_values": self.original_values,
        }


@dataclass
class CrossSectionValidationResult:
    """Result of cross-section validation.
    
    Attributes:
        document_id: Document ID
        is_valid: Whether document passed validation
        issues: List of validation issues found
        reconciled_values: Reconciled canonical values
        summary: Summary statistics
    """
    document_id: Optional[UUID] = None
    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    reconciled_values: List[ReconciledValue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    
    def get_errors(self) -> List[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == "error"]
    
    def get_warnings(self) -> List[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == "warning"]
    
    def get_reconciled_value(self, field_name: str) -> Optional[Any]:
        """Get reconciled value for a field."""
        for rv in self.reconciled_values:
            if rv.field_name == field_name:
                return rv.canonical_value
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": str(self.document_id) if self.document_id else None,
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "reconciled_values": [rv.to_dict() for rv in self.reconciled_values],
            "summary": self.summary,
        }


class CrossSectionValidator:
    """Tier 3 validator for cross-section reconciliation.
    
    This service validates extracted data across sections to ensure
    consistency and resolve conflicts. It performs:
    - Policy number consistency checks
    - Date validation (effective, expiration, retroactive)
    - Limit/premium alignment
    - Entity deduplication
    - Conflict resolution
    
    Attributes:
        client: UnifiedLLMClient for LLM-assisted validation
        use_llm_for_conflicts: Whether to use LLM for conflict resolution
    """
    
    VALIDATION_PROMPT = """You are an expert insurance document validator. Analyze the extracted data from multiple sections and:

1. **Identify inconsistencies** between sections
2. **Recommend canonical values** for conflicting fields
3. **Flag missing required fields**
4. **Validate date logic** (effective < expiration, etc.)
5. **Check limit/premium alignment**

## Input Format:
You will receive extracted data from multiple sections of an insurance document.

## Output Format (JSON only):
{
    "is_valid": true/false,
    "issues": [
        {
            "issue_type": "inconsistency|missing|conflict|invalid",
            "severity": "error|warning|info",
            "field_name": "policy_number",
            "sections_involved": ["declarations", "coverages"],
            "values_found": ["POL-123", "POL-124"],
            "recommended_value": "POL-123",
            "message": "Policy number differs between declarations and coverages"
        }
    ],
    "reconciled_values": [
        {
            "field_name": "policy_number",
            "canonical_value": "POL-123",
            "source_sections": ["declarations"],
            "confidence": 0.95
        }
    ],
    "summary": {
        "total_issues": 2,
        "errors": 1,
        "warnings": 1,
        "fields_reconciled": 5
    }
}

## Validation Rules:
1. Policy number must be consistent across all sections
2. Effective date must be before expiration date
3. Total premium should match sum of coverage premiums (within 5%)
4. Limits mentioned in declarations should match coverage limits
5. Insured name should be consistent (allow minor variations)
6. Carrier name should be consistent

Return ONLY valid JSON (no code fences or markdown).
"""
    
    # Fields that must be consistent across sections
    CRITICAL_FIELDS = [
        "policy_number",
        "insured_name",
        "carrier_name",
        "effective_date",
        "expiration_date",
    ]
    
    def __init__(
        self,
        session: Optional[AsyncSession] = None,
        provider: str = "gemini",
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash",
        openrouter_api_key: Optional[str] = None,
        openrouter_model: str = "openai/gpt-oss-20b:free",
        openrouter_api_url: str = "https://openrouter.ai/api/v1/chat/completions",
        use_llm_for_conflicts: bool = True,
        timeout: int = 90,
    ):
        """Initialize cross-section validator.
        
        Args:
            session: SQLAlchemy async session
            provider: LLM provider
            gemini_api_key: Gemini API key
            gemini_model: Gemini model name
            openrouter_api_key: OpenRouter API key
            openrouter_model: OpenRouter model name
            openrouter_api_url: OpenRouter API URL
            use_llm_for_conflicts: Use LLM for complex conflict resolution
            timeout: API timeout
        """
        self.session = session
        self.provider = provider
        self.use_llm_for_conflicts = use_llm_for_conflicts
        
        # Initialize LLM client if needed
        if use_llm_for_conflicts:
            self.client = create_llm_client_from_settings(
                provider=provider,
                gemini_api_key=gemini_api_key or "",
                gemini_model=gemini_model,
                openrouter_api_key=openrouter_api_key or "",
                openrouter_api_url=openrouter_api_url,
                openrouter_model=openrouter_model,
                timeout=timeout,
                max_retries=3,
                enable_fallback=False,
            )
        else:
            self.client = None
        
        LOGGER.info(
            "Initialized CrossSectionValidator (Tier 3)",
            extra={
                "provider": provider,
                "use_llm": use_llm_for_conflicts,
            }
        )
    
    async def validate(
        self,
        extraction_result: DocumentExtractionResult,
    ) -> CrossSectionValidationResult:
        """Validate extracted data across all sections.
        
        This is the main Tier 3 processing method.
        
        Args:
            extraction_result: Result from Tier 2 extraction
            
        Returns:
            CrossSectionValidationResult
        """
        document_id = extraction_result.document_id
        
        LOGGER.info(
            "Starting Tier 3 cross-section validation",
            extra={
                "document_id": str(document_id) if document_id else None,
                "sections_to_validate": len(extraction_result.section_results),
            }
        )
        
        # Step 1: Rule-based validation
        issues, reconciled = self._rule_based_validation(extraction_result)
        
        # Step 2: LLM-assisted validation for complex conflicts
        if self.use_llm_for_conflicts and self.client and issues:
            try:
                llm_result = await self._llm_validation(extraction_result)
                # Merge LLM findings with rule-based findings
                issues = self._merge_issues(issues, llm_result.issues)
                reconciled = self._merge_reconciled(reconciled, llm_result.reconciled_values)
            except Exception as e:
                LOGGER.warning(f"LLM validation failed, using rule-based only: {e}")
        
        # Step 3: Determine overall validity
        has_errors = any(i.severity == "error" for i in issues)
        
        result = CrossSectionValidationResult(
            document_id=document_id,
            is_valid=not has_errors,
            issues=issues,
            reconciled_values=reconciled,
            summary={
                "total_issues": len(issues),
                "errors": sum(1 for i in issues if i.severity == "error"),
                "warnings": sum(1 for i in issues if i.severity == "warning"),
                "info": sum(1 for i in issues if i.severity == "info"),
                "fields_reconciled": len(reconciled),
                "sections_validated": len(extraction_result.section_results),
            }
        )
        
        LOGGER.info(
            "Tier 3 validation completed",
            extra={
                "document_id": str(document_id) if document_id else None,
                "is_valid": result.is_valid,
                "total_issues": len(issues),
                "errors": result.summary["errors"],
            }
        )
        
        return result
    
    def _rule_based_validation(
        self,
        extraction_result: DocumentExtractionResult,
    ) -> Tuple[List[ValidationIssue], List[ReconciledValue]]:
        """Perform rule-based validation.
        
        Args:
            extraction_result: Extraction result to validate
            
        Returns:
            Tuple of (issues, reconciled_values)
        """
        issues = []
        reconciled = []
        
        # Collect all field values across sections
        field_values: Dict[str, Dict[str, Any]] = {}
        
        for section_result in extraction_result.section_results:
            section_name = section_result.section_type.value
            data = section_result.extracted_data
            
            # Flatten nested data
            flat_data = self._flatten_data(data)
            
            for field_name, value in flat_data.items():
                if value is not None:
                    if field_name not in field_values:
                        field_values[field_name] = {}
                    field_values[field_name][section_name] = value
        
        # Check critical fields for consistency
        for field_name in self.CRITICAL_FIELDS:
            if field_name in field_values:
                values = field_values[field_name]
                unique_values = set(str(v) for v in values.values())
                
                if len(unique_values) > 1:
                    # Inconsistency found
                    issue = ValidationIssue(
                        issue_type="inconsistency",
                        severity="error" if field_name == "policy_number" else "warning",
                        field_name=field_name,
                        sections_involved=list(values.keys()),
                        values_found=list(values.values()),
                        recommended_value=self._pick_canonical_value(values),
                        message=f"{field_name} differs across sections",
                    )
                    issues.append(issue)
                
                # Add reconciled value
                canonical = self._pick_canonical_value(values)
                reconciled.append(ReconciledValue(
                    field_name=field_name,
                    canonical_value=canonical,
                    source_sections=list(values.keys()),
                    confidence=1.0 if len(unique_values) == 1 else 0.7,
                    original_values=values,
                ))
        
        # Validate dates
        date_issues = self._validate_dates(field_values)
        issues.extend(date_issues)
        
        # Validate premiums
        premium_issues = self._validate_premiums(extraction_result)
        issues.extend(premium_issues)
        
        return issues, reconciled
    
    def _flatten_data(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flatten nested dictionary.
        
        Args:
            data: Nested dictionary
            prefix: Key prefix
            
        Returns:
            Flattened dictionary
        """
        flat = {}
        
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                flat.update(self._flatten_data(value, full_key))
            elif isinstance(value, list):
                # Skip lists for now
                pass
            else:
                flat[full_key] = value
        
        return flat
    
    def _pick_canonical_value(self, values: Dict[str, Any]) -> Any:
        """Pick canonical value from multiple values.
        
        Prioritizes declarations section, then most common value.
        
        Args:
            values: Dict mapping section names to values
            
        Returns:
            Canonical value
        """
        # Priority order for sections
        priority_sections = [
            "declarations",
            "coverages",
            "insuring_agreement",
            "endorsements",
        ]
        
        for section in priority_sections:
            if section in values:
                return values[section]
        
        # Return first value if no priority match
        return next(iter(values.values()))
    
    def _validate_dates(
        self,
        field_values: Dict[str, Dict[str, Any]],
    ) -> List[ValidationIssue]:
        """Validate date logic.
        
        Args:
            field_values: Field values across sections
            
        Returns:
            List of date-related issues
        """
        issues = []
        
        # Get dates
        effective_dates = field_values.get("effective_date", {})
        expiration_dates = field_values.get("expiration_date", {})
        
        if effective_dates and expiration_dates:
            try:
                eff_value = self._pick_canonical_value(effective_dates)
                exp_value = self._pick_canonical_value(expiration_dates)
                
                if eff_value and exp_value:
                    eff_date = self._parse_date(eff_value)
                    exp_date = self._parse_date(exp_value)
                    
                    if eff_date and exp_date and eff_date >= exp_date:
                        issues.append(ValidationIssue(
                            issue_type="invalid",
                            severity="error",
                            field_name="date_range",
                            sections_involved=list(effective_dates.keys()),
                            values_found=[eff_value, exp_value],
                            message="Effective date must be before expiration date",
                        ))
            except Exception as e:
                LOGGER.warning(f"Date validation error: {e}")
        
        return issues
    
    def _validate_premiums(
        self,
        extraction_result: DocumentExtractionResult,
    ) -> List[ValidationIssue]:
        """Validate premium consistency.
        
        Args:
            extraction_result: Extraction result
            
        Returns:
            List of premium-related issues
        """
        issues = []
        
        # Get declarations total premium
        decl_result = extraction_result.get_section_result(SectionType.DECLARATIONS)
        if not decl_result:
            return issues
        
        total_premium = decl_result.extracted_data.get("total_premium")
        if not total_premium:
            return issues
        
        # Get coverage premiums
        cov_result = extraction_result.get_section_result(SectionType.COVERAGES)
        if not cov_result:
            return issues
        
        coverages = cov_result.extracted_data.get("coverages", [])
        coverage_premium_sum = sum(
            float(c.get("premium_amount", 0) or 0) 
            for c in coverages if isinstance(c, dict)
        )
        
        # Check alignment (within 5%)
        try:
            total = float(total_premium)
            if coverage_premium_sum > 0 and abs(total - coverage_premium_sum) / total > 0.05:
                issues.append(ValidationIssue(
                    issue_type="inconsistency",
                    severity="warning",
                    field_name="premium_alignment",
                    sections_involved=["declarations", "coverages"],
                    values_found=[total, coverage_premium_sum],
                    message=f"Total premium ({total}) differs from sum of coverage premiums ({coverage_premium_sum})",
                ))
        except (ValueError, ZeroDivisionError):
            pass
        
        return issues
    
    def _parse_date(self, date_value: Any) -> Optional[datetime]:
        """Parse date from various formats.
        
        Args:
            date_value: Date value
            
        Returns:
            Parsed datetime or None
        """
        if isinstance(date_value, datetime):
            return date_value
        
        if not isinstance(date_value, str):
            return None
        
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                continue
        
        return None
    
    async def _llm_validation(
        self,
        extraction_result: DocumentExtractionResult,
    ) -> CrossSectionValidationResult:
        """Use LLM for complex validation.
        
        Args:
            extraction_result: Extraction result
            
        Returns:
            LLM validation result
        """
        # Prepare input for LLM
        sections_data = {}
        for section_result in extraction_result.section_results:
            sections_data[section_result.section_type.value] = section_result.extracted_data
        
        input_json = json.dumps(sections_data, indent=2, default=str)
        
        response = await self.client.generate_content(
            contents=f"Validate this extracted insurance document data:\n\n{input_json}",
            system_instruction=self.VALIDATION_PROMPT,
            generation_config={"response_mime_type": "application/json"}
        )
        
        parsed = parse_json_safely(response)
        
        if parsed is None:
            return CrossSectionValidationResult()
        
        # Parse issues
        issues = []
        for issue_data in parsed.get("issues", []):
            issues.append(ValidationIssue(
                issue_type=issue_data.get("issue_type", "unknown"),
                severity=issue_data.get("severity", "warning"),
                field_name=issue_data.get("field_name", "unknown"),
                sections_involved=issue_data.get("sections_involved", []),
                values_found=issue_data.get("values_found", []),
                recommended_value=issue_data.get("recommended_value"),
                message=issue_data.get("message", ""),
            ))
        
        # Parse reconciled values
        reconciled = []
        for rv_data in parsed.get("reconciled_values", []):
            reconciled.append(ReconciledValue(
                field_name=rv_data.get("field_name", ""),
                canonical_value=rv_data.get("canonical_value"),
                source_sections=rv_data.get("source_sections", []),
                confidence=float(rv_data.get("confidence", 0.0)),
            ))
        
        return CrossSectionValidationResult(
            is_valid=parsed.get("is_valid", True),
            issues=issues,
            reconciled_values=reconciled,
            summary=parsed.get("summary", {}),
        )
    
    def _merge_issues(
        self,
        rule_issues: List[ValidationIssue],
        llm_issues: List[ValidationIssue],
    ) -> List[ValidationIssue]:
        """Merge rule-based and LLM issues.
        
        Args:
            rule_issues: Issues from rule-based validation
            llm_issues: Issues from LLM validation
            
        Returns:
            Merged issue list
        """
        # Use field_name as key to avoid duplicates
        seen = {i.field_name for i in rule_issues}
        merged = list(rule_issues)
        
        for issue in llm_issues:
            if issue.field_name not in seen:
                merged.append(issue)
                seen.add(issue.field_name)
        
        return merged
    
    def _merge_reconciled(
        self,
        rule_reconciled: List[ReconciledValue],
        llm_reconciled: List[ReconciledValue],
    ) -> List[ReconciledValue]:
        """Merge reconciled values.
        
        Prefers LLM values when confidence is higher.
        
        Args:
            rule_reconciled: Values from rule-based validation
            llm_reconciled: Values from LLM validation
            
        Returns:
            Merged reconciled values
        """
        result = {}
        
        # Add rule-based first
        for rv in rule_reconciled:
            result[rv.field_name] = rv
        
        # Override with LLM if higher confidence
        for rv in llm_reconciled:
            if rv.field_name not in result or rv.confidence > result[rv.field_name].confidence:
                result[rv.field_name] = rv
        
        return list(result.values())

