"""Quote Comparison Service - Core comparison engine.

Compares carrier quotes at coverage level, generating side-by-side
matrix, identifying gaps, and producing broker-facing outputs.
"""

from uuid import UUID
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.product.quote_comparison import (
    CanonicalCoverage,
    CoverageQualityScore,
    CoverageComparisonRow,
    CoverageGap,
    MaterialDifference,
    PricingAnalysis,
    QuoteComparisonSummary,
    QuoteComparisonResult,
)
from app.services.product.shared.shared_comparison_service import SharedComparisonService
from app.services.product.quote_comparison.coverage_normalization_service import CoverageNormalizationService
from app.services.product.quote_comparison.coverage_quality_service import CoverageQualityService
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.workflow_output_repository import WorkflowOutputRepository
from app.services.product.quote_comparison.reasoning_service import QuoteComparisonReasoningService
from app.database.models import WorkflowOutput
from app.temporal.product.quote_comparison.configs.quote_comparison import (
    NUMERIC_FIELDS_CONFIG,
    WORKFLOW_NAME,
)
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)


class QuoteComparisonService:
    """Service for comparing carrier quotes."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.section_repo = SectionExtractionRepository(session)
        self.output_repo = WorkflowOutputRepository(session)
        self.shared_service = SharedComparisonService()
        self.normalization_service = CoverageNormalizationService(session)
        self.quality_service = CoverageQualityService()
        self.reasoning_service = QuoteComparisonReasoningService()
    
    async def compare_quotes(
        self,
        workflow_id: UUID,
        document_ids: list[UUID],
    ) -> QuoteComparisonResult:
        """Compare carrier quotes with optional ACORD and Proposal context.
        
        Args:
            workflow_id: Current workflow ID
            document_ids: List of document UUIDs (at least 2 quotes)
            
        Returns:
            QuoteComparisonResult with complete comparison data
        """
        from app.repositories.page_analysis_repository import PageAnalysisRepository
        from app.models.page_analysis_models import DocumentType

        # 1. Identify roles
        quotes = []
        acord_doc = None
        proposal_doc = None
        
        page_analysis_repo = PageAnalysisRepository(self.session)
        
        for doc_id in document_ids:
            profile = await page_analysis_repo.get_document_profile(doc_id)
            if not profile:
                # If no profile, try to infer or skip
                continue
            
            if profile.document_type == DocumentType.QUOTE:
                quotes.append(doc_id)
            elif profile.document_type == DocumentType.ACORD_APPLICATION:
                acord_doc = doc_id
            elif profile.document_type == DocumentType.PROPOSAL:
                proposal_doc = doc_id
        
        if len(quotes) < 2:
            # Fallback to first two if types aren't clear but we were told to compare
            if not quotes and len(document_ids) >= 2:
                quotes = document_ids[:2]
            else:
                raise ValueError(f"Quote comparison requires at least 2 quotes, found {len(quotes)}")
        
        # Primary quotes for side-by-side
        doc1_id, doc2_id = quotes[0], quotes[1]
        
        # 2. Normalize coverages
        coverages_q1 = await self.normalization_service.normalize_coverages_for_document(
            doc1_id, workflow_id
        )
        coverages_q2 = await self.normalization_service.normalize_coverages_for_document(
            doc2_id, workflow_id
        )
        
        coverages_requested = []
        if acord_doc:
            coverages_requested = await self.normalization_service.normalize_coverages_for_document(
                acord_doc, workflow_id
            )
        
        # 3. Evaluate quality scores
        scores_q1 = self.quality_service.evaluate_quality(coverages_q1)
        scores_q2 = self.quality_service.evaluate_quality(coverages_q2)
        
        # 4. Build comparison matrix
        comparison_matrix = self._build_comparison_matrix(
            coverages_q1, coverages_q2, scores_q1, scores_q2, coverages_requested
        )
        
        # 5. Identify coverage gaps (including against ACORD)
        coverage_gaps = self._identify_coverage_gaps(
            coverages_q1, coverages_q2, comparison_matrix, coverages_requested
        )
        
        # 6. Identify material differences
        material_differences = await self._identify_material_differences(
            workflow_id, doc1_id, doc2_id
        )
        
        # 7. Compare pricing
        pricing_analysis = await self._compare_pricing(
            workflow_id, doc1_id, doc2_id
        )
        
        # 8. Build summary
        high_severity_count = sum(
            1 for g in coverage_gaps if g.severity == "high"
        ) + sum(
            1 for d in material_differences if d.severity == "high"
        )
        
        overall_confidence = self._calculate_overall_confidence(
            coverages_q1, coverages_q2
        )
        
        summary = QuoteComparisonSummary(
            total_coverages_compared=len(comparison_matrix),
            coverage_gaps_count=len(coverage_gaps),
            material_differences_count=len(material_differences),
            high_severity_count=high_severity_count,
            overall_confidence=overall_confidence,
            comparison_scope="full"
        )
        
        quote_comparison_result = QuoteComparisonResult(
            comparison_summary=summary,
            comparison_matrix=comparison_matrix,
            coverage_gaps=coverage_gaps,
            material_differences=material_differences,
            pricing_analysis=pricing_analysis,
            broker_summary=None,
            metadata={
                "workflow_id": str(workflow_id),
                "quote1_id": str(doc1_id),
                "quote2_id": str(doc2_id),
                "acord_id": str(acord_doc) if acord_doc else None,
                "proposal_id": str(proposal_doc) if proposal_doc else None,
                "coverages_q1_count": len(coverages_q1),
                "coverages_q2_count": len(coverages_q2),
                "coverages_requested_count": len(coverages_requested),
            }
        )
        
        return quote_comparison_result
    
    def _build_comparison_matrix(
        self,
        coverages_q1: list[CanonicalCoverage],
        coverages_q2: list[CanonicalCoverage],
        scores_q1: list[CoverageQualityScore],
        scores_q2: list[CoverageQualityScore],
        coverages_requested: Optional[list[CanonicalCoverage]] = None,
    ) -> list[CoverageComparisonRow]:
        """Build side-by-side coverage comparison matrix."""
        # Build lookups
        q1_map = {c.canonical_coverage: c for c in coverages_q1}
        q2_map = {c.canonical_coverage: c for c in coverages_q2}
        req_map = {c.canonical_coverage: c for c in coverages_requested} if coverages_requested else {}
        scores1_map = {s.canonical_coverage: s for s in scores_q1}
        scores2_map = {s.canonical_coverage: s for s in scores_q2}
        
        all_coverages = set(q1_map.keys()) | set(q2_map.keys()) | set(req_map.keys())
        
        rows = []
        for cov_name in sorted(all_coverages):
            cov1 = q1_map.get(cov_name)
            cov2 = q2_map.get(cov_name)
            score1 = scores1_map.get(cov_name)
            score2 = scores2_map.get(cov_name)
            
            # Extract values
            q1_limit = cov1.limit.value if cov1 else None
            q2_limit = cov2.limit.value if cov2 else None
            q1_deductible = cov1.deductible if cov1 else None
            q2_deductible = cov2.deductible if cov2 else None
            
            # Calculate differences
            limit_diff = None
            if q1_limit is not None and q2_limit is not None:
                limit_diff = q2_limit - q1_limit
            
            # Determine advantages
            limit_adv = self.shared_service.determine_advantage(
                q1_limit, q2_limit, higher_is_better=True
            )
            ded_adv = self.shared_service.determine_advantage(
                q1_deductible, q2_deductible, higher_is_better=False
            )
            
            row = CoverageComparisonRow(
                broker_note="",
                canonical_coverage=cov_name,
                category=cov1.category if cov1 else (cov2.category if cov2 else "add_on"),
                quote1_present=cov1 is not None,
                quote1_limit=q1_limit,
                quote1_deductible=q1_deductible,
                quote1_premium=None,
                quote1_included=cov1.included if cov1 else None,
                quote2_present=cov2 is not None,
                quote2_limit=q2_limit,
                quote2_deductible=q2_deductible,
                quote2_premium=None,
                quote2_included=cov2.included if cov2 else None,
                limit_difference=limit_diff,
                limit_advantage=limit_adv,
                deductible_advantage=ded_adv,
                quality_score_quote1=score1.total_score if score1 else None,
                quality_score_quote2=score2.total_score if score2 else None,
                # Requested baseline
                requested_present=cov_name in req_map,
                requested_limit=req_map[cov_name].limit.value if cov_name in req_map else None,
                requested_deductible=req_map[cov_name].deductible if cov_name in req_map else None,
            )
            rows.append(row)
        
        return rows
    
    def _identify_coverage_gaps(
        self,
        coverages_q1: list[CanonicalCoverage],
        coverages_q2: list[CanonicalCoverage],
        comparison_matrix: list[CoverageComparisonRow],
        coverages_requested: Optional[list[CanonicalCoverage]] = None,
    ) -> list[CoverageGap]:
        """Identify coverage gaps between quotes and relative to ACORD."""
        gaps = []
        
        q1_names = {c.canonical_coverage for c in coverages_q1}
        q2_names = {c.canonical_coverage for c in coverages_q2}
        
        # Missing coverages
        for name in q1_names - q2_names:
            cov = next(c for c in coverages_q1 if c.canonical_coverage == name)
            gaps.append(CoverageGap(
                canonical_coverage=name,
                gap_type="missing_in_quote2",
                severity="high" if cov.is_base else "medium",
                description=f"Coverage '{name}' is present in Quote 1 but missing in Quote 2",
                affected_quote="quote2"
            ))
        
        for name in q2_names - q1_names:
            cov = next(c for c in coverages_q2 if c.canonical_coverage == name)
            gaps.append(CoverageGap(
                canonical_coverage=name,
                gap_type="missing_in_quote1",
                severity="high" if cov.is_base else "medium",
                description=f"Coverage '{name}' is present in Quote 2 but missing in Quote 1",
                affected_quote="quote1"
            ))
        
        # Check for inadequate limits or high deductibles
        for row in comparison_matrix:
            if row.quote1_present and row.quote2_present:
                # Check if one has significantly lower limit
                if row.limit_difference and abs(row.limit_difference) > Decimal("50000"):
                    lower_quote = "quote1" if row.limit_advantage == "quote2" else "quote2"
                    gaps.append(CoverageGap(
                        canonical_coverage=row.canonical_coverage,
                        gap_type="limit_inadequate",
                        severity="medium",
                        description=f"Significant limit difference of ${abs(row.limit_difference):,.0f} for {row.canonical_coverage}",
                        affected_quote=lower_quote  # type: ignore
                    ))
            
            # Gap Analysis vs ACORD Requested
            if row.requested_present:
                if not row.quote1_present:
                    gaps.append(CoverageGap(
                        canonical_coverage=row.canonical_coverage,
                        gap_type="missing_relative_to_acord",
                        severity="high",
                        description=f"Requested coverage '{row.canonical_coverage}' is missing in Quote 1",
                        affected_quote="quote1"
                    ))
                elif row.requested_limit and row.quote1_limit and row.quote1_limit < row.requested_limit:
                    gaps.append(CoverageGap(
                        canonical_coverage=row.canonical_coverage,
                        gap_type="limit_below_requested",
                        severity="medium",
                        description=f"Quote 1 limit for '{row.canonical_coverage}' is below requested amount",
                        affected_quote="quote1"
                    ))
                
                if not row.quote2_present:
                    gaps.append(CoverageGap(
                        canonical_coverage=row.canonical_coverage,
                        gap_type="missing_relative_to_acord",
                        severity="high",
                        description=f"Requested coverage '{row.canonical_coverage}' is missing in Quote 2",
                        affected_quote="quote2"
                    ))
                elif row.requested_limit and row.quote2_limit and row.quote2_limit < row.requested_limit:
                    gaps.append(CoverageGap(
                        canonical_coverage=row.canonical_coverage,
                        gap_type="limit_below_requested",
                        severity="medium",
                        description=f"Quote 2 limit for '{row.canonical_coverage}' is below requested amount",
                        affected_quote="quote2"
                    ))
        
        return gaps
    
    async def _identify_material_differences(
        self,
        workflow_id: UUID,
        doc1_id: UUID,
        doc2_id: UUID
    ) -> list[MaterialDifference]:
        """Identify material differences across all sections."""
        differences = []
        
        # Fetch sections for both documents
        sections1 = await self.section_repo.get_by_document_and_workflow(doc1_id, workflow_id)
        sections2 = await self.section_repo.get_by_document_and_workflow(doc2_id, workflow_id)
        
        # Build section maps
        s1_map = {s.section_type: s for s in sections1}
        s2_map = {s.section_type: s for s in sections2}
        
        all_sections = set(s1_map.keys()) | set(s2_map.keys())
        
        for section_type in all_sections:
            s1 = s1_map.get(section_type)
            s2 = s2_map.get(section_type)
            
            if s1 and s2:
                if "entities" in s1.extracted_fields and isinstance(s1.extracted_fields["entities"], list) and s1.extracted_fields["entities"]:
                    fields1 = s1.extracted_fields["entities"]
                if "entities" in s2.extracted_fields and isinstance(s2.extracted_fields["entities"], list) and s2.extracted_fields["entities"]:
                    fields2 = s2.extracted_fields["entities"]
                
                section_diffs = self._compare_fields(
                    fields1, fields2, section_type
                )
                differences.extend(section_diffs)
        
        return differences
    
    def _compare_fields(
        self,
        fields1: dict,
        fields2: dict,
        section_type: str
    ) -> list[MaterialDifference]:
        """Compare extracted fields between two sections."""
        diffs = []
        all_keys = set(fields1.keys()) | set(fields2.keys())
        
        # Sections where we want to include identical fields for audit
        audit_sections = ["declarations", "endorsements", "exclusions", "conditions"]
        
        for key in all_keys:
            val1 = fields1.get(key)
            val2 = fields2.get(key)
            
            if val1 == val2:
                if section_type in audit_sections:
                    diffs.append(MaterialDifference(
                        field_name=key,
                        section_type=section_type,
                        quote1_value=val1,
                        quote2_value=val2,
                        change_type="identical",
                        percent_change=None,
                        severity="low",
                        broker_note=None
                    ))
                continue
            
            # Determine change type
            if val1 is None:
                change_type = "added"
            elif val2 is None:
                change_type = "removed"
            elif self.shared_service.is_numeric(val1) and self.shared_service.is_numeric(val2):
                num1 = self.shared_service.parse_numeric(val1)
                num2 = self.shared_service.parse_numeric(val2)
                if num1 and num2:
                    result = self.shared_service.compare_numeric_fields(
                        num1, num2, key, NUMERIC_FIELDS_CONFIG
                    )
                    change_type = result["change_type"]
                    diffs.append(MaterialDifference(
                        field_name=key,
                        section_type=section_type,
                        quote1_value=val1,
                        quote2_value=val2,
                        change_type=change_type,  # type: ignore
                        percent_change=result.get("percent_change"),
                        severity=result["severity"],  # type: ignore
                        broker_note=None
                    ))
                    continue
            else:
                change_type = "modified"
            
            # Default severity for non-numeric
            severity = "medium"
            
            diffs.append(MaterialDifference(
                field_name=key,
                section_type=section_type,
                quote1_value=val1,
                quote2_value=val2,
                change_type=change_type,
                percent_change=None,
                severity=severity,
                broker_note=None
            ))
        
        return diffs
    
    async def _compare_pricing(
        self,
        workflow_id: UUID,
        doc1_id: UUID,
        doc2_id: UUID
    ) -> PricingAnalysis:
        """Compare pricing between quotes."""
        # Fetch premium sections
        sections1 = await self.section_repo.get_by_document_and_workflow(doc1_id, workflow_id)
        sections2 = await self.section_repo.get_by_document_and_workflow(doc2_id, workflow_id)
        
        premium1 = Decimal("0")
        premium2 = Decimal("0")
        
        for s in sections1:
            if s.section_type in ["premiums", "premium", "declarations"]:
                if "entities" in s.extracted_fields and isinstance(s.extracted_fields["entities"], list) and s.extracted_fields["entities"]:
                    fields = s.extracted_fields["entities"] or {}
                    if "total_premium" in fields:
                        premium1 = self.shared_service.parse_numeric(fields["total_premium"]) or Decimal("0")
                        break
        
        for s in sections2:
            if s.section_type in ["premiums", "premium", "declarations"]:
                if "entities" in s.extracted_fields and isinstance(s.extracted_fields["entities"], list) and s.extracted_fields["entities"]:
                    fields = s.extracted_fields["entities"] or {}
                    if "total_premium" in fields:
                        premium2 = self.shared_service.parse_numeric(fields["total_premium"]) or Decimal("0")
                        break
        
        diff = premium2 - premium1
        pct_change = ((premium2 - premium1) / premium1 * 100) if premium1 != 0 else Decimal("0")
        
        return PricingAnalysis(
            quote1_total_premium=premium1,
            quote2_total_premium=premium2,
            premium_difference=diff,
            premium_percent_change=pct_change,
            lower_premium_quote=self.shared_service.determine_advantage(
                premium1, premium2, higher_is_better=False
            ),
            fee_comparison=None,
            payment_terms_comparison=None
        )
    
    def _calculate_overall_confidence(
        self,
        coverages_q1: list[CanonicalCoverage],
        coverages_q2: list[CanonicalCoverage]
    ) -> Decimal:
        """Calculate overall comparison confidence."""
        confidences = [c.confidence for c in coverages_q1 + coverages_q2]
        if not confidences:
            return Decimal("0.0")
        return sum(confidences) / len(confidences)
    
    async def finalize_comparison_result(
        self,
        workflow_id: UUID,
        workflow_definition_id: UUID,
        document_ids: list[UUID],
        result: QuoteComparisonResult,
        broker_summary: Optional[str] = None
    ) -> dict:
        """Finalize and persist comparison result to WorkflowOutput."""
        # Add broker summary if provided
        if broker_summary:
            result.broker_summary = broker_summary
        
        # Determine status
        status = "COMPLETED"
        if result.comparison_summary.high_severity_count > 0:
            status = "COMPLETED_WITH_WARNINGS"
        if result.comparison_summary.overall_confidence < Decimal("0.7"):
            status = "NEEDS_REVIEW"
        
        # Create WorkflowOutput
        output = WorkflowOutput(
            workflow_id=workflow_id,
            workflow_definition_id=workflow_definition_id,
            workflow_name=WORKFLOW_NAME,
            status=status,
            confidence=result.comparison_summary.overall_confidence,
            result=result.model_dump(mode="json"),
            output_metadata={
                "document_ids": [str(d) for d in document_ids],
                "warnings": [g.description for g in result.coverage_gaps if g.severity == "high"],
            }
        )
        
        await self.output_repo.create(output)
        await self.session.commit()
        
        return {
            "status": status,
            "comparison_summary": result.comparison_summary.model_dump(mode="json"),
            "total_changes": (
                result.comparison_summary.coverage_gaps_count + 
                result.comparison_summary.material_differences_count
            ),
        }
