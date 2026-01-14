"""Detailed comparison service for Policy Comparison workflow."""

import re
import math
from uuid import UUID
from typing import Optional, Literal, Any
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.schemas.workflows.policy_comparison import ComparisonChange, SectionProvenance
from app.temporal.configs.policy_comparison import (
    NUMERIC_FIELDS_CONFIG,
    EXCLUDED_FIELDS,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class DetailedComparisonService:
    """Service for computing detailed differences between policy documents.
    
    Compares all extracted fields across aligned sections, handling:
    - Numeric differences (with severity)
    - Text differences (formatting vs material)
    - Date differences (sequential logic)
    - Structured data (nested dicts/lists)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = SectionExtractionRepository(session)

    async def compute_comparison(
        self,
        aligned_sections: list,
    ) -> list[ComparisonChange]:
        """Compute detailed differences for aligned sections.
        
        Args:
            aligned_sections: List of SectionAlignment objects
            
        Returns:
            List of ComparisonChange objects representing all fields
        """
        LOGGER.info(
            f"Computing detailed comparison for {len(aligned_sections)} aligned sections"
        )

        all_changes = []

        for alignment in aligned_sections:
            # Fetch section data
            doc1_section = await self.section_repo.get_by_id(alignment.doc1_section_id)
            doc2_section = await self.section_repo.get_by_id(alignment.doc2_section_id)

            if not doc1_section or not doc2_section:
                LOGGER.warning(f"Section not found for alignment: {alignment}")
                continue

            # Recursively compare extracted fields
            section_changes = self._compare_recursive(
                doc1_section.extracted_fields,
                doc2_section.extracted_fields,
                path_prefix="",
                section_type=alignment.section_type,
                provenance=SectionProvenance(
                    doc1_section_id=doc1_section.id,
                    doc2_section_id=doc2_section.id,
                    doc1_page_range=doc1_section.page_range,
                    doc2_page_range=doc2_section.page_range,
                ),
                context={}
            )
            all_changes.extend(section_changes)

        LOGGER.info(
            f"Detailed comparison completed: {len(all_changes)} items processed"
        )

        return all_changes

    def _compare_recursive(
        self,
        val1: Any,
        val2: Any,
        path_prefix: str,
        section_type: str,
        provenance: SectionProvenance,
        context: Dict[str, Any],
    ) -> list[ComparisonChange]:
        """Recursively compare two values (dict, list, or scalar)."""
        changes = []
        
        # Merge values into context if they look like identifying fields
        new_context = context.copy()
        if isinstance(val1, dict):
            # Prioritize specific identifiers
            ident_keys = ["coverage_name", "name", "label", "id", "type", "description"]
            for k in ident_keys:
                if k in val1 and val1[k]:
                    new_context[k] = val1[k]
                    break
        elif isinstance(val2, dict):
            ident_keys = ["coverage_name", "name", "label", "id", "type", "description"]
            for k in ident_keys:
                if k in val2 and val2[k]:
                    new_context[k] = val2[k]
                    break

        # Handle Dictionaries
        if isinstance(val1, dict) and isinstance(val2, dict):
            keys = set(val1.keys()) | set(val2.keys())
            for key in keys:
                if key in EXCLUDED_FIELDS:
                    continue
                
                new_path = f"{path_prefix}.{key}" if path_prefix else key
                v1 = val1.get(key)
                v2 = val2.get(key)
                
                changes.extend(
                    self._compare_recursive(v1, v2, new_path, section_type, provenance, new_context)
                )
            return changes

        # Handle Lists (simple index-based or length comparison for now)
        # TODO: Implement smarter list alignment (e.g. by ID or key field) if needed
        if isinstance(val1, list) and isinstance(val2, list):
            # For lists, we'll iterate up to the max length
            max_len = max(len(val1), len(val2))
            for i in range(max_len):
                new_path = f"{path_prefix}[{i}]"
                v1 = val1[i] if i < len(val1) else None
                v2 = val2[i] if i < len(val2) else None
                
                changes.extend(
                    self._compare_recursive(v1, v2, new_path, section_type, provenance, new_context)
                )
            return changes

        # Handle Scalars (Leaf nodes)
        return [
            self._compare_values(val1, val2, path_prefix, section_type, provenance, new_context)
        ]

    def _compare_values(
        self,
        val1: Any,
        val2: Any,
        field_name: str,
        section_type: str,
        provenance: SectionProvenance,
        context: Dict[str, Any],
    ) -> ComparisonChange:
        """Compare two scalar values and determine change type/severity."""
        
        # Initial check for nulls
        if val1 is None and val2 is None:
             return ComparisonChange(
                field_name=field_name,
                section_type=section_type,
                coverage_name=None,
                old_value=None,
                new_value=None,
                change_type="no_change",
                percent_change=None,
                absolute_change=None,
                severity="low",
                provenance=provenance,
             )

        change_type = "no_change"
        severity = "low"
        percent_change = None
        absolute_change = None
        
        # 1. Check for Added/Removed
        if val1 is None and val2 is not None:
            change_type = "added"
            severity = "medium" # default for added info? Or high?
        elif val1 is not None and val2 is None:
            change_type = "removed"
            severity = "medium"
        
        # 2. Check for Equality
        elif val1 == val2:
            change_type = "no_change"
            severity = "low"
        
        # 3. Numeric Comparison
        elif self._is_numeric(val1) and self._is_numeric(val2):
            n1 = Decimal(str(val1))
            n2 = Decimal(str(val2))
            
            absolute_change = n2 - n1
            if n1 != 0:
                percent_change = (absolute_change / n1) * 100
                
            if n2 > n1:
                change_type = "increase"
            elif n2 < n1:
                change_type = "decrease"
            else:
                change_type = "no_change"
                
            # Calculate numeric severity
            severity = self._calculate_numeric_severity(field_name, percent_change)
            
            # Clean up values for return
            val1 = n1
            val2 = n2

        # 4. Text/Date Comparison
        else:
            s1 = str(val1)
            s2 = str(val2)
            
            # Formatting check
            if self._clean_string(s1) == self._clean_string(s2):
                change_type = "formatting_diff"
                severity = "low"
            else:
                # Sequential check for dates?
                # A simple heuristic: if it looks like a date and diff is exactly 1 year?
                # For now, general "modified"
                change_type = "modified"
                severity = "low" # Text changes are low by default unless specific fields

                # Check if it's "SEQUENTIAL" (e.g. year changed from 2017 to 2018)
                # This could be noisy, so maybe only for "date" fields
                if "date" in field_name.lower():
                     if self._is_sequential_date(s1, s2):
                         change_type = "sequential"
                         severity = "low"

        # Determine coverage_name from context
        coverage_name = context.get("coverage_name") or context.get("name") or context.get("label") or context.get("description")

        return ComparisonChange(
            field_name=field_name,
            section_type=section_type,
            coverage_name=coverage_name,
            old_value=val1,
            new_value=val2,
            change_type=change_type,
            percent_change=percent_change,
            absolute_change=absolute_change,
            severity=severity,
            provenance=provenance,
        )

    def _is_numeric(self, val: Any) -> bool:
        """Check if value can be treated as numeric."""
        if isinstance(val, bool):
            return False
        if isinstance(val, (int, float, Decimal)):
            return True
        try:
            float(str(val))
            return True
        except (ValueError, TypeError):
            return False

    def _clean_string(self, s: str) -> str:
        """Normalize string for formatting check."""
        # Remove special chars, lower case
        return re.sub(r'[\W_]+', '', s.lower())

    def _calculate_numeric_severity(
        self, field_name: str, percent_change: Optional[Decimal]
    ) -> Literal["low", "medium", "high"]:
        """Get severity from config or default."""
        if percent_change is None:
            return "low"
            
        # Try exact match or partial match on field name keys
        config = None
        for key in NUMERIC_FIELDS_CONFIG:
            if key in field_name:
                config = NUMERIC_FIELDS_CONFIG[key]
                break
        
        if not config:
            return "low"
            
        abs_change = abs(percent_change)
        if abs_change < config["low"]:
            return "low"
        elif abs_change < config["medium"]:
            return "medium"
        else:
            return "high"

    def _is_sequential_date(self, d1_str: str, d2_str: str) -> bool:
        """Check if dates are sequential (e.g. ~1 year apart)."""
        try:
            # Simple ISO date parsing (YYYY-MM-DD)
            # In production, use robust parser
            d1 = datetime.strptime(d1_str[:10], "%Y-%m-%d")
            d2 = datetime.strptime(d2_str[:10], "%Y-%m-%d")
            
            diff = abs((d2 - d1).days)
            # 365 or 366 days
            return 360 <= diff <= 370
        except ValueError:
            return False
