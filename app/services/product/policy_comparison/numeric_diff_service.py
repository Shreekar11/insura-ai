"""Numeric diff service for Policy Comparison workflow."""

from uuid import UUID
from typing import Optional, Literal
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.schemas.workflows.policy_comparison import ComparisonChange, SectionProvenance
from app.temporal.configs.policy_comparison import (
    NUMERIC_FIELDS_CONFIG,
    FIELD_PATHS,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class NumericDiffService:
    """Service for computing numeric differences between policy documents.
    
    Compares numeric fields like limits, deductibles, and premiums across
    aligned sections and classifies changes by severity.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = SectionExtractionRepository(session)

    async def compute_numeric_diffs(
        self,
        aligned_sections: list,
        fields: Optional[list[str]] = None,
    ) -> list[ComparisonChange]:
        """Compute numeric differences for aligned sections.
        
        Args:
            aligned_sections: List of SectionAlignment objects
            fields: Optional list of field names to compare (defaults to all configured fields)
            
        Returns:
            List of ComparisonChange objects representing numeric differences
        """
        if fields is None:
            fields = list(NUMERIC_FIELDS_CONFIG.keys())

        LOGGER.info(
            f"Computing numeric diffs for {len(aligned_sections)} aligned sections",
            extra={"section_count": len(aligned_sections), "fields": fields}
        )

        all_changes = []

        for alignment in aligned_sections:
            # Fetch section data
            doc1_section = await self.section_repo.get_by_id(alignment.doc1_section_id)
            doc2_section = await self.section_repo.get_by_id(alignment.doc2_section_id)

            if not doc1_section or not doc2_section:
                LOGGER.warning(f"Section not found for alignment: {alignment}")
                continue

            # Compare each numeric field
            for field_name in fields:
                change = await self._compare_numeric_field(
                    field_name,
                    doc1_section,
                    doc2_section,
                    alignment.section_type,
                )
                if change:
                    all_changes.append(change)

        LOGGER.info(
            f"Numeric diff computation completed: {len(all_changes)} changes detected",
            extra={"change_count": len(all_changes)}
        )

        return all_changes

    async def _compare_numeric_field(
        self,
        field_name: str,
        doc1_section,
        doc2_section,
        section_type: str,
    ) -> Optional[ComparisonChange]:
        """Compare a single numeric field across two sections.
        
        Args:
            field_name: Name of the field to compare
            doc1_section: First section extraction
            doc2_section: Second section extraction
            section_type: Type of section being compared
            
        Returns:
            ComparisonChange object if a change is detected, None otherwise
        """
        # Extract numeric values
        old_value = self._extract_numeric_value(doc1_section.extracted_fields, field_name)
        new_value = self._extract_numeric_value(doc2_section.extracted_fields, field_name)

        # Skip if both values are missing
        if old_value is None and new_value is None:
            return None

        # Determine change type
        change_type = self._classify_change(old_value, new_value)

        # Calculate percent and absolute change
        percent_change = None
        absolute_change = None

        if old_value is not None and new_value is not None:
            absolute_change = new_value - old_value
            if old_value != 0:
                percent_change = (absolute_change / old_value) * 100

        # Determine severity
        severity = self._calculate_severity(field_name, percent_change, change_type)

        # Build provenance
        provenance = SectionProvenance(
            doc1_section_id=doc1_section.id,
            doc2_section_id=doc2_section.id,
            doc1_page_range=doc1_section.page_range,
            doc2_page_range=doc2_section.page_range,
        )

        return ComparisonChange(
            field_name=field_name,
            section_type=section_type,
            coverage_name=None,  # TODO: Extract coverage name if applicable
            old_value=old_value,
            new_value=new_value,
            change_type=change_type,
            percent_change=percent_change,
            absolute_change=absolute_change,
            severity=severity,
            provenance=provenance,
        )

    def _extract_numeric_value(
        self, section_data: dict, field_name: str
    ) -> Optional[Decimal]:
        """Safely extract numeric value from JSONB section data.
        
        Tries multiple field paths to find the value.
        
        Args:
            section_data: JSONB extracted_fields dictionary
            field_name: Name of the field to extract
            
        Returns:
            Decimal value if found, None otherwise
        """
        # Get possible field paths for this field
        paths = FIELD_PATHS.get(field_name, [field_name])

        for path in paths:
            # Support nested paths (e.g., "limits.occurrence_limit")
            if "." in path:
                value = self._get_nested_value(section_data, path.split("."))
            else:
                value = section_data.get(path)

            if value is not None:
                try:
                    return Decimal(str(value))
                except (ValueError, TypeError):
                    continue

        return None

    def _get_nested_value(self, data: dict, path: list[str]):
        """Get value from nested dictionary using path list."""
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _classify_change(
        self, old_value: Optional[Decimal], new_value: Optional[Decimal]
    ) -> Literal["increase", "decrease", "no_change", "added", "removed"]:
        """Classify the type of change between two values."""
        if old_value is None and new_value is not None:
            return "added"
        elif old_value is not None and new_value is None:
            return "removed"
        elif old_value == new_value:
            return "no_change"
        elif new_value > old_value:
            return "increase"
        else:
            return "decrease"

    def _calculate_severity(
        self,
        field_name: str,
        percent_change: Optional[Decimal],
        change_type: str,
    ) -> Literal["low", "medium", "high"]:
        """Assign severity level based on percent change and business rules.
        
        Args:
            field_name: Name of the field
            percent_change: Percentage change (can be negative)
            change_type: Type of change (increase, decrease, etc.)
            
        Returns:
            Severity level: low, medium, or high
        """
        # Added or removed fields are always high severity
        if change_type in ["added", "removed"]:
            return "high"

        # No change is low severity
        if change_type == "no_change":
            return "low"

        # Get severity thresholds for this field
        thresholds = NUMERIC_FIELDS_CONFIG.get(field_name, {
            "low": 5.0,
            "medium": 15.0,
            "high": 15.0,
        })

        if percent_change is None:
            return "low"

        # Use absolute value for comparison
        abs_change = abs(percent_change)

        if abs_change < thresholds["low"]:
            return "low"
        elif abs_change < thresholds["medium"]:
            return "medium"
        else:
            return "high"
