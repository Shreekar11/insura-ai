"""Service for generating natural language reasoning for quote comparisons."""

import json
from decimal import Decimal
from typing import List, Dict, Any, Optional
from app.core.unified_llm import UnifiedLLMClient
from app.core.config import settings
from app.schemas.product.quote_comparison import (
    MaterialDifference,
    CoverageComparisonRow,
    QuoteComparisonResult,
)
from app.utils.logging import get_logger
from app.utils.json_parser import parse_json_safely

LOGGER = get_logger(__name__)

class QuoteComparisonReasoningService:
    """Generates natural language explanations for quote differences and similarities."""

    def __init__(self):
        self.client = UnifiedLLMClient(
            provider=settings.llm_provider,
            api_key=settings.gemini_api_key if settings.llm_provider == "gemini" else settings.openrouter_api_key,
            model=settings.gemini_model if settings.llm_provider == "gemini" else settings.openrouter_model,
            base_url=settings.openrouter_api_url if settings.llm_provider == "openrouter" else None,
        )

    async def enrich_comparison_result(self, result: QuoteComparisonResult) -> QuoteComparisonResult:
        """Enriches the comparison result with natural language reasoning."""
        
        # 1. Enrich Material Differences
        result.material_differences = await self.enrich_material_differences(
            result.material_differences
        )
        
        # 2. Enrich Coverage Rows
        result.comparison_matrix = await self.enrich_coverage_rows(
            result.comparison_matrix
        )
        
        result.broker_summary = await self.generate_overall_summary(result)
            
        return result

    async def enrich_material_differences(
        self, differences: List[MaterialDifference]
    ) -> List[MaterialDifference]:
        """Enriches material differences with broker notes."""
        if not differences:
            return []

        # Process deterministic cases first
        remaining_diffs = []
        for diff in differences:
            if diff.change_type == "identical":
                diff.broker_note = f"Found {diff.field_name.replace('_', ' ')} in both Quotes as same."
            else:
                remaining_diffs.append(diff)

        if not remaining_diffs:
            return differences

        # Batch process remaining diffs with LLM
        groups = {}
        for diff in remaining_diffs:
            section = diff.section_type
            if section not in groups:
                groups[section] = []
            groups[section].append(diff)

        enriched_diff_map = {id(d): d for d in differences}

        for section_type, section_diffs in groups.items():
            try:
                batch_data = [
                    {
                        "id": id(d),
                        "field": d.field_name,
                        "q1": str(d.quote1_value),
                        "q2": str(d.quote2_value),
                        "type": d.change_type
                    }
                    for d in section_diffs
                ]

                prompt = self._get_batch_reasoning_prompt(section_type, batch_data)
                
                response = await self.client.generate_content(
                    contents=prompt,
                    generation_config={"response_mime_type": "application/json"}
                )

                reasoning_results = parse_json_safely(response)
                if isinstance(reasoning_results, list):
                    for item in reasoning_results:
                        diff_id = item.get("id")
                        reason = item.get("reason")
                        if diff_id in enriched_diff_map:
                            enriched_diff_map[diff_id].broker_note = reason

            except Exception as e:
                LOGGER.error(f"Failed to generate reasoning for section {section_type}: {e}", exc_info=True)

        return list(enriched_diff_map.values())

    async def enrich_coverage_rows(
        self, rows: List[CoverageComparisonRow]
    ) -> List[CoverageComparisonRow]:
        """Enriches coverage comparison rows with broker notes."""
        if not rows:
            return []

        # Coverages often have deterministic logic
        for row in rows:
            if row.quote1_present and row.quote2_present:
                if row.quote1_limit == row.quote2_limit and row.quote1_deductible == row.quote2_deductible:
                    row.broker_note = f"Both quotes provide identical limits and deductibles for {row.canonical_coverage.replace('_', ' ')}."
                elif row.limit_difference and abs(row.limit_difference) > 0:
                    adv = "advantageous" if row.limit_advantage == "quote2" else "lower"
                    diff_amt = abs(row.limit_difference)
                    row.broker_note = f"Quote 2 offers a ${diff_amt:,.0f} {adv} difference in limits compared to Quote 1."
            elif not row.quote1_present:
                row.broker_note = f"Coverage for {row.canonical_coverage.replace('_', ' ')} is missing in Quote 1."
            elif not row.quote2_present:
                row.broker_note = f"Coverage for {row.canonical_coverage.replace('_', ' ')} is missing in Quote 2."

        return rows

    async def generate_overall_summary(self, result: QuoteComparisonResult) -> str:
        """Generates a high-level summary of the quote comparison."""
        
        material_changes = [d for d in result.material_differences if d.change_type != "identical" and d.severity in ["medium", "high"]]
        gaps = result.coverage_gaps
        
        if not material_changes and not gaps:
            return "Both quotes are substantially similar with no major coverage gaps identified."

        summary_parts = []
        for d in material_changes[:10]:
            summary_parts.append(f"- {d.section_type}: {d.field_name} differs ({d.quote1_value} vs {d.quote2_value})")
        
        for g in gaps[:5]:
            summary_parts.append(f"- Gap: {g.description}")

        prompt = (
            "You are an insurance expert. Summarize the key differences between two carrier quotes for a broker. "
            "Focus on significant limit changes, coverage gaps, and premium differences. "
            "Keep it professional and concise (3-4 sentences).\n\n"
            "Data:\n" + "\n".join(summary_parts) + "\n\n"
            "Summary:"
        )

        try:
            response = await self.client.generate_content(contents=prompt)
            return response.strip()
        except Exception as e:
            LOGGER.error(f"Failed to generate overall summary: {e}", exc_info=True)
            return "Quote comparison summary generation failed."

    def _get_batch_reasoning_prompt(self, section_type: str, batch_data: List[Dict]) -> str:
        return f"""You are an insurance technical auditor. Compare the following field-level differences in the '{section_type}' section of two carrier quotes.
For each item, provide a very short, natural language explanation (one sentence max) for the broker.
Example: "Quote 2 provides a higher limit for Cyber Liability, offering better protection against data breaches."

Input Data (JSON):
{json.dumps(batch_data)}

Return a JSON list of objects with "id" and "reason" fields.
Example Output:
[
  {{"id": 12345, "reason": "The deductible was reduced in Quote 2, lower out-of-pocket costs for the insured."}}
]
"""
