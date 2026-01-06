"""Summarized stage - Human/system-facing outputs."""

from .facade import SummarizedStageFacade
from .contracts import SummaryResult, EmbeddingResult
from .services.generate_summary import GenerateSummaryService
from .services.generate_embeddings import GenerateEmbeddingsService

__all__ = [
    "SummarizedStageFacade",
    "SummaryResult",
    "EmbeddingResult",
    "GenerateSummaryService",
    "GenerateEmbeddingsService",
]
