"""Shared comparison service for Policy and Quote Comparison workflows.

Provides common comparison logic that can be reused across both workflows.
"""

import re
from decimal import Decimal
from typing import Optional, Literal, Any


class SharedComparisonService:
    """Shared comparison logic for Policy and Quote workflows."""
    
    def compare_numeric_fields(
        self,
        val1: Optional[Decimal],
        val2: Optional[Decimal],
        field_name: str,
        config: Optional[dict[str, dict[str, float]]] = None
    ) -> dict:
        """Reusable numeric comparison with severity calculation.
        
        Args:
            val1: Value from first document
            val2: Value from second document
            field_name: Name of the field being compared
            config: Optional severity thresholds config
            
        Returns:
            Dict with change_type, absolute_change, percent_change, severity
        """
        # Handle missing values
        if val1 is None and val2 is None:
            return {
                "change_type": "no_change",
                "absolute_change": None,
                "percent_change": None,
                "severity": "low"
            }
        
        if val1 is None:
            return {
                "change_type": "added",
                "absolute_change": val2,
                "percent_change": None,
                "severity": "medium"
            }
        
        if val2 is None:
            return {
                "change_type": "removed",
                "absolute_change": val1,
                "percent_change": None,
                "severity": "medium"
            }
        
        # Both values present - calculate difference
        absolute_change = val2 - val1
        
        if val1 != 0:
            percent_change = ((val2 - val1) / abs(val1)) * 100
        else:
            percent_change = Decimal("100.0") if val2 != 0 else Decimal("0.0")
        
        # Determine change type
        if absolute_change > 0:
            change_type = "increase"
        elif absolute_change < 0:
            change_type = "decrease"
        else:
            change_type = "no_change"
        
        # Calculate severity
        severity = self.calculate_change_severity(
            field_name, abs(percent_change), config
        )
        
        return {
            "change_type": change_type,
            "absolute_change": absolute_change,
            "percent_change": percent_change,
            "severity": severity
        }
    
    def detect_formatting_diff(self, str1: str, str2: str) -> bool:
        """Detect if strings differ only by formatting.
        
        Returns True if the strings are semantically the same but differ
        in formatting (whitespace, punctuation, case).
        """
        if str1 == str2:
            return False  # No difference at all
        
        cleaned1 = self._clean_string(str1)
        cleaned2 = self._clean_string(str2)
        
        return cleaned1.lower() == cleaned2.lower()
    
    def _clean_string(self, s: str) -> str:
        """Normalize string for formatting check."""
        # Remove extra whitespace, punctuation variations
        s = re.sub(r'[\s_\-*]+', ' ', s)
        s = re.sub(r'[^\w\s]', '', s)
        return s.strip()
    
    def calculate_change_severity(
        self,
        field_name: str,
        percent_change: Decimal,
        config: Optional[dict[str, dict[str, float]]] = None
    ) -> Literal["low", "medium", "high"]:
        """Field-specific severity thresholds.
        
        Args:
            field_name: Name of the field
            percent_change: Absolute percentage change
            config: Optional config with per-field thresholds
            
        Returns:
            Severity level: low, medium, or high
        """
        # Default thresholds
        default_thresholds = {
            "low": 5.0,
            "medium": 15.0,
            "high": 15.0  # Anything above medium threshold is high
        }
        
        # Get field-specific thresholds if available
        if config and field_name in config:
            thresholds = config[field_name]
        else:
            thresholds = default_thresholds
        
        pct = float(percent_change)
        
        if pct <= thresholds.get("low", 5.0):
            return "low"
        elif pct <= thresholds.get("medium", 15.0):
            return "medium"
        else:
            return "high"
    
    def is_numeric(self, val: Any) -> bool:
        """Check if value can be treated as numeric."""
        if val is None:
            return False
        if isinstance(val, (int, float, Decimal)):
            return True
        if isinstance(val, str):
            try:
                Decimal(val.replace(",", "").replace("$", "").strip())
                return True
            except:
                return False
        return False
    
    def parse_numeric(self, val: Any) -> Optional[Decimal]:
        """Parse a value as Decimal, handling common formats."""
        if val is None:
            return None
        if isinstance(val, Decimal):
            return val
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        if isinstance(val, str):
            try:
                cleaned = val.replace(",", "").replace("$", "").strip()
                return Decimal(cleaned)
            except:
                return None
        return None
    
    def determine_advantage(
        self,
        val1: Optional[Decimal],
        val2: Optional[Decimal],
        higher_is_better: bool = True
    ) -> Literal["quote1", "quote2", "equal"]:
        """Determine which quote has the advantage for a field.
        
        Args:
            val1: Value from quote 1
            val2: Value from quote 2
            higher_is_better: If True, higher value is better (e.g., limits)
                            If False, lower value is better (e.g., deductibles, premiums)
        """
        if val1 is None and val2 is None:
            return "equal"
        if val1 is None:
            return "quote2"
        if val2 is None:
            return "quote1"
        
        if val1 == val2:
            return "equal"
        
        if higher_is_better:
            return "quote1" if val1 > val2 else "quote2"
        else:
            return "quote1" if val1 < val2 else "quote2"
