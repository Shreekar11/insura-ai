"""Table classification service for identifying table types.

This service classifies tables as:
- property_sov (Statement of Values)
- loss_run
- inland_marine_schedule
- auto_schedule
- premium_schedule
- other

Classification is rules-based.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.services.processed.services.table.table_extraction_service import TableStructure, TableClassification
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class ClassificationRule:
    """Rule for table classification."""
    
    table_type: str
    header_keywords: List[str]
    column_keywords: List[str]
    min_matches: int = 1


class TableClassificationService:
    """Service for classifying table types based on headers and structure.
    
    Uses rules-based classification (not LLM) per Phase 5 requirements.
    """
    
    # Classification rules for different table types
    CLASSIFICATION_RULES = [
        ClassificationRule(
            table_type="property_sov",
            header_keywords=[
                "statement of values", "sov", "schedule of values",
                "location", "address", "building", "contents", "tiv", "total insured value",
                "total stated values", "scheduled locations", "schedule of locations"
            ],
            column_keywords=[
                # Location identifiers
                "loc", "loc #", "loc#", "location", "address", "bldg", "bldg #", "bldg#",
                # Value columns
                "building", "building value", "contents", "business personal property",
                "tenant improvements", "betterments", "business income", "extra expense",
                "bi", "tiv", "total", "total values", "insured value", "total insured value",
                "additional property", "coverage",
                # Property characteristics
                "description", "distance to coast", "flood zone", "construction", "occupancy",
                "year built", "square feet", "sq ft"
            ],
            min_matches=2  # Lowered threshold since real tables may have fewer exact matches
        ),
        ClassificationRule(
            table_type="loss_run",
            header_keywords=[
                "loss run", "claims", "loss history", "claim history",
                "claim summary", "loss summary", "claims report"
            ],
            column_keywords=[
                "claim", "claim #", "claim number", "loss date", "date of loss",
                "incurred", "paid", "reserve", "status", "cause", "cause of loss",
                "policy number", "policy", "claimant", "adjuster", "settlement"
            ],
            min_matches=2
        ),
        ClassificationRule(
            table_type="inland_marine_schedule",
            header_keywords=[
                "inland marine", "schedule", "equipment", "machinery"
            ],
            column_keywords=[
                "item", "description", "location", "value", "coverage"
            ],
            min_matches=2
        ),
        ClassificationRule(
            table_type="auto_schedule",
            header_keywords=[
                "auto", "vehicle", "fleet", "schedule"
            ],
            column_keywords=[
                "year", "make", "model", "vin", "value", "coverage"
            ],
            min_matches=3
        ),
        ClassificationRule(
            table_type="premium_schedule",
            header_keywords=[
                "premium", "coverage", "limit", "premium amount"
            ],
            column_keywords=[
                "coverage", "limit", "premium", "deductible", "rate"
            ],
            min_matches=2
        ),
    ]
    
    def __init__(self):
        """Initialize table classification service."""
        LOGGER.info("Initialized TableClassificationService")
    
    def classify_table(
        self,
        table: TableStructure,
        page_context: Optional[str] = None
    ) -> TableClassification:
        """Classify a table based on headers and structure.
        
        Args:
            table: TableStructure to classify
            page_context: Optional page text for context
            
        Returns:
            TableClassification with type and confidence
        """
        if not table.headers:
            return TableClassification(
                table_type="other",
                confidence=0.0,
                reasoning="No headers found"
            )
        
        # Normalize headers for matching
        header_text = " ".join(table.headers).lower()
        all_text = header_text
        if page_context:
            all_text += " " + page_context.lower()
        
        best_match = None
        best_score = 0.0
        
        for rule in self.CLASSIFICATION_RULES:
            score = self._calculate_match_score(rule, header_text, all_text, table)
            if score > best_score:
                best_score = score
                best_match = rule
        
        # Require higher confidence for property_sov to avoid false positives
        min_confidence = 0.5 if best_match and best_match.table_type == "property_sov" else 0.3
        
        # Additional check: if headers contain policy number patterns, it's likely not an SOV
        if best_match and best_match.table_type == "property_sov":
            import re
            policy_pattern = re.compile(r'policy\s*number|policy\s*#', re.IGNORECASE)
            if policy_pattern.search(header_text):
                # This looks like a policy info table, not an SOV
                return TableClassification(
                    table_type="other",
                    confidence=0.0,
                    reasoning="Headers contain 'policy number' - likely not an SOV table"
                )
        
        if best_match and best_score >= min_confidence:
            return TableClassification(
                table_type=best_match.table_type,
                confidence=min(best_score, 1.0),
                reasoning=f"Matched {best_match.table_type} rule with score {best_score:.2f}"
            )
        
        return TableClassification(
            table_type="other",
            confidence=0.0,
            reasoning=f"No matching classification rule (best score: {best_score:.2f}, required: {min_confidence})"
        )
    
    def _calculate_match_score(
        self,
        rule: ClassificationRule,
        header_text: str,
        all_text: str,
        table: TableStructure
    ) -> float:
        """Calculate match score for a classification rule.
        
        Args:
            rule: Classification rule to match
            header_text: Normalized header text
            all_text: All available text (headers + context)
            table: Table structure
            
        Returns:
            Match score between 0.0 and 1.0
        """
        score = 0.0
        
        # Check header keywords in page context (e.g., "STATEMENT OF VALUES" heading)
        # This is a strong signal
        context_matches = sum(
            1 for keyword in rule.header_keywords
            if keyword.lower() in all_text and keyword.lower() not in header_text
        )
        if context_matches > 0:
            score += 0.35 * min(context_matches, 2) / 2  # Strong boost for context match
        
        # Check column keywords in table headers
        column_matches = sum(
            1 for keyword in rule.column_keywords
            if keyword.lower() in header_text
        )
        if column_matches > 0:
            # Normalize by expected matches (not total keywords)
            expected_matches = min(5, len(rule.column_keywords))
            score += 0.45 * min(column_matches, expected_matches) / expected_matches
        
        # Check if minimum matches requirement is met
        total_matches = context_matches + column_matches
        if total_matches < rule.min_matches:
            score *= 0.5  # Penalize if minimum matches not met
        else:
            score += 0.1  # Bonus for meeting minimum
        
        # Bonus for table structure matching expected columns
        if rule.table_type == "property_sov" and table.num_columns >= 5:
            score += 0.1
        elif rule.table_type == "loss_run" and table.num_columns >= 6:
            score += 0.1
        
        LOGGER.debug(
            f"Classification score for {rule.table_type}: {score:.2f}",
            extra={
                "table_type": rule.table_type,
                "context_matches": context_matches,
                "column_matches": column_matches,
                "total_matches": total_matches,
                "min_matches": rule.min_matches,
                "num_columns": table.num_columns,
                "score": score
            }
        )
        
        return min(score, 1.0)

