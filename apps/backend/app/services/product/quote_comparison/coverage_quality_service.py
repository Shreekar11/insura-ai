"""Coverage Quality Service for Quote Comparison workflow.

Implements the coverage quality scoring formula:
Score = Coverage Presence + Limit Adequacy - Deductible Penalty - Exclusion Risk
"""

from decimal import Decimal
from typing import Optional

from app.schemas.product.quote_comparison import (
    CanonicalCoverage,
    CoverageQualityScore,
)
from app.temporal.product.quote_comparison.configs.quote_comparison import (
    QUALITY_SCORE_WEIGHTS,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


# Reference limits for adequacy evaluation (industry benchmarks)
REFERENCE_LIMITS: dict[str, Decimal] = {
    "dwelling": Decimal("500000"),
    "other_structures": Decimal("50000"),
    "personal_property": Decimal("250000"),
    "loss_of_use": Decimal("100000"),
    "personal_liability": Decimal("300000"),
    "medical_payments": Decimal("5000"),
    "general_liability": Decimal("1000000"),
    "umbrella_liability": Decimal("1000000"),
    "business_income": Decimal("250000"),
}

# Deductible thresholds for penalty calculation
DEDUCTIBLE_THRESHOLDS: dict[str, dict[str, Decimal]] = {
    "property": {
        "low": Decimal("500"),
        "medium": Decimal("1000"),
        "high": Decimal("2500"),
    },
    "liability": {
        "low": Decimal("0"),
        "medium": Decimal("1000"),
        "high": Decimal("5000"),
    },
}


class CoverageQualityService:
    """Service for evaluating coverage quality scores."""
    
    def __init__(self):
        self.weights = QUALITY_SCORE_WEIGHTS
    
    def evaluate_quality(
        self,
        canonical_coverages: list[CanonicalCoverage],
        reference_coverages: Optional[list[CanonicalCoverage]] = None
    ) -> list[CoverageQualityScore]:
        """Score each coverage.
        
        Args:
            canonical_coverages: List of normalized coverages to score
            reference_coverages: Optional reference coverages for comparison
            
        Returns:
            List of CoverageQualityScore objects
        """
        scores = []
        
        for coverage in canonical_coverages:
            score = self._score_coverage(coverage, reference_coverages)
            scores.append(score)
        
        return scores
    
    def _score_coverage(
        self,
        coverage: CanonicalCoverage,
        reference_coverages: Optional[list[CanonicalCoverage]] = None
    ) -> CoverageQualityScore:
        """Calculate quality score for a single coverage.
        
        Formula: Score = Coverage Presence + Limit Adequacy 
                        - Deductible Penalty - Exclusion Risk
        """
        # 1. Coverage Presence (1.0 if present, 0.0 if not)
        presence_score = Decimal("1.0") * Decimal(str(self.weights.get("coverage_presence", 1.0)))
        
        # 2. Limit Adequacy (0.0 - 1.0 based on how close to reference)
        limit_adequacy = self._calculate_limit_adequacy(coverage)
        adequacy_score = limit_adequacy * Decimal(str(self.weights.get("limit_adequacy", 0.8)))
        
        # 3. Deductible Penalty (0.0 - 1.0, higher deductible = higher penalty)
        deductible_penalty = self._calculate_deductible_penalty(coverage)
        penalty_score = deductible_penalty * Decimal(str(abs(self.weights.get("deductible_penalty", -0.3))))
        
        # 4. Exclusion Risk (placeholder - would need exclusion analysis)
        exclusion_risk = Decimal("0.0")  # TODO: Integrate with exclusion analysis
        exclusion_score = exclusion_risk * Decimal(str(abs(self.weights.get("exclusion_risk", -0.4))))
        
        # Total score
        total = presence_score + adequacy_score - penalty_score - exclusion_score
        
        # Normalize to 0-10 scale
        total_normalized = min(max(total * Decimal("10"), Decimal("0")), Decimal("10"))
        
        return CoverageQualityScore(
            canonical_coverage=coverage.canonical_coverage,
            coverage_presence=presence_score,
            limit_adequacy=adequacy_score,
            deductible_penalty=penalty_score,
            exclusion_risk=exclusion_score,
            total_score=total_normalized
        )
    
    def _calculate_limit_adequacy(self, coverage: CanonicalCoverage) -> Decimal:
        """Calculate limit adequacy score (0.0 - 1.0).
        
        Compares actual limit to reference/benchmark limit.
        """
        reference_limit = REFERENCE_LIMITS.get(
            coverage.canonical_coverage,
            Decimal("100000")  # Default reference
        )
        
        actual_limit = coverage.limit.value if coverage.limit else Decimal("0")
        
        if reference_limit == 0:
            return Decimal("1.0")
        
        # Calculate ratio
        ratio = actual_limit / reference_limit
        
        # Cap at 1.0 (meeting or exceeding reference is full score)
        return min(ratio, Decimal("1.0"))
    
    def _calculate_deductible_penalty(self, coverage: CanonicalCoverage) -> Decimal:
        """Calculate deductible penalty (0.0 - 1.0).
        
        Higher deductible = higher penalty.
        """
        if coverage.deductible is None:
            return Decimal("0.0")  # No deductible = no penalty
        
        category = coverage.category
        thresholds = DEDUCTIBLE_THRESHOLDS.get(category, DEDUCTIBLE_THRESHOLDS["property"])
        
        deductible = coverage.deductible
        
        if deductible <= thresholds["low"]:
            return Decimal("0.0")
        elif deductible <= thresholds["medium"]:
            return Decimal("0.3")
        elif deductible <= thresholds["high"]:
            return Decimal("0.6")
        else:
            return Decimal("1.0")  # Very high deductible
    
    def compare_quality_scores(
        self,
        scores_quote1: list[CoverageQualityScore],
        scores_quote2: list[CoverageQualityScore]
    ) -> dict:
        """Compare quality scores between two quotes.
        
        Returns summary of which quote has better quality overall.
        """
        # Build lookup by coverage name
        scores1_map = {s.canonical_coverage: s for s in scores_quote1}
        scores2_map = {s.canonical_coverage: s for s in scores_quote2}
        
        all_coverages = set(scores1_map.keys()) | set(scores2_map.keys())
        
        quote1_total = Decimal("0")
        quote2_total = Decimal("0")
        coverage_comparisons = []
        
        for cov_name in all_coverages:
            score1 = scores1_map.get(cov_name)
            score2 = scores2_map.get(cov_name)
            
            s1 = score1.total_score if score1 else Decimal("0")
            s2 = score2.total_score if score2 else Decimal("0")
            
            quote1_total += s1
            quote2_total += s2
            
            coverage_comparisons.append({
                "coverage": cov_name,
                "quote1_score": float(s1),
                "quote2_score": float(s2),
                "advantage": (
                    "quote1" if s1 > s2 else 
                    "quote2" if s2 > s1 else 
                    "equal"
                )
            })
        
        return {
            "quote1_total_quality": float(quote1_total),
            "quote2_total_quality": float(quote2_total),
            "overall_advantage": (
                "quote1" if quote1_total > quote2_total else
                "quote2" if quote2_total > quote1_total else
                "equal"
            ),
            "coverage_comparisons": coverage_comparisons
        }
