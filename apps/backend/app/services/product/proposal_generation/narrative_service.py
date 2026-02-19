"""Service for generating natural language narratives for policy proposals."""

from typing import List, Dict, Any
from app.schemas.product.policy_comparison import ComparisonChange
from app.core.unified_llm import UnifiedLLMClient
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class ProposalNarrativeService:
    """Generates professional narratives for proposal sections.
    
    Instead of browsing raw text, this service uses the structured 
    ComparisonChange data to summarize key findings.
    """
    
    def __init__(self, client: UnifiedLLMClient):
        """Initialize with LLM client."""
        self.client = client

    async def generate_section_narrative(
        self, 
        section_type: str, 
        changes: List[ComparisonChange]
    ) -> str:
        """Generate a narrative summary for a specific section."""
        if not changes:
            return f"No material changes detected in the {section_type} section."

        # Filter for meaningful changes (ignore no_change and formatting_diff)
        meaningful_changes = [
            c for c in changes 
            if c.change_type not in ["no_change", "formatting_diff"]
        ]
        
        if not meaningful_changes:
            return f"The {section_type} remains consistent with the expiring policy."

        # Summarize changes for the prompt
        summary_data = []
        for c in meaningful_changes:
            summary_data.append({
                "field": c.field_name,
                "coverage": c.canonical_coverage_name or c.coverage_name,
                "delta": c.delta_type,
                "old": str(c.old_value),
                "new": str(c.new_value),
                "severity": c.severity
            })

        prompt = f"""
        You are an elite Commercial Insurance Broker.
        Generate a professional narrative summary for the '{section_type}' section of a renewal proposal.
        
        CONTEXT:
        We are comparing the Expiring policy against the Renewal quote.
        
        DATA:
        {summary_data}
        
        RULES:
        1. Be concise and professional.
        2. Highlight 'ADVANTAGE' items as benefits of the renewal.
        3. Explain 'GAP' items clearly but conservatively.
        4. Mention significant limit increases or deductible decreases.
        5. Tone should be expert and advisory.
        6. Max 3-4 sentences.
        
        NARRATIVE:
        """
        
        try:
            response = await self.client.generate_content(
                contents=prompt,
                generation_config={"temperature": 0.2}
            )
            return response.text.strip()
        except Exception as e:
            LOGGER.error(f"Failed to generate narrative for {section_type}: {e}")
            return "Professional summary currently unavailable."

    async def generate_executive_summary(
        self, 
        all_changes: List[ComparisonChange]
    ) -> str:
        """Generate a high-level executive summary for the whole proposal."""
        # Top 5 most severe/critical changes
        critical_changes = sorted(
            [c for c in all_changes if c.delta_type in ["GAP", "ADVANTAGE"] or c.severity == "high"],
            key=lambda x: (x.severity == "high", x.delta_type == "GAP"),
            reverse=True
        )[:5]
        
        summary_items = []
        for c in critical_changes:
            summary_items.append(
                f"- {c.delta_type}: {c.canonical_coverage_name or c.field_name} "
                f"({c.old_value} -> {c.new_value})"
            )

        prompt = f"""
        You are an elite Commercial Insurance Broker writing an Executive Summary for a renewal proposal.
        
        KEY FINDINGS:
        {summary_items}
        
        TASK:
        Write a single, high-impact paragraph that summarizes the state of the renewal vs expiring and provides a strategic recommendation.
        
        Rules:
        1. Be punchy and professional.
        2. Highlight the most critical value (e.g. premium savings or coverage gap fix).
        3. Max 5 sentences.
        
        Tone: Professional, persuasive, and advisory.
        """
        
        try:
            response = await self.client.generate_content(
                contents=prompt,
                generation_config={"temperature": 0.3}
            )
            return response.text.strip()
        except Exception as e:
            LOGGER.error(f"Failed to generate executive summary: {e}")
            return "Executive summary currently unavailable."
