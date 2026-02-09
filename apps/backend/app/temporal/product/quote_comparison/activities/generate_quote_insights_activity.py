from typing import Any
from temporalio import activity
from app.services.product.quote_comparison.reasoning_service import QuoteComparisonReasoningService
from app.schemas.product.quote_comparison import QuoteComparisonResult
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

@activity.defn
async def generate_quote_insights_activity(
    comparison_result: dict
) -> dict:
    """
    Generate natural language insights and broker summary for the quote comparison.
    
    Args:
        comparison_result: The raw QuoteComparisonResult dictionary
        
    Returns:
        The enriched QuoteComparisonResult dictionary with reasoning and summary
    """
    LOGGER.info("Starting quote insights generation")
    
    try:
        # Re-hydrate pydantic model
        result_model = QuoteComparisonResult(**comparison_result)
        
        service = QuoteComparisonReasoningService()
        
        # Enrich with reasoning
        enriched_result = await service.enrich_comparison_result(result_model)
        
        LOGGER.info("Quote insights generation completed")
        
        return enriched_result.model_dump(mode="json")
        
    except Exception as e:
        LOGGER.error(f"Quote insights generation failed: {e}", exc_info=True)
        # Return original result on failure to avoid blocking workflow
        return comparison_result
