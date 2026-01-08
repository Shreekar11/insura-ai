"""Summarized stage - Human/system-facing outputs."""

from .facade import SummarizedStageFacade
from .contracts import SummaryResult, EmbeddingResult
from .services.summary.generate_summary import GenerateSummaryService
from .services.indexing.vector.generate_embeddings import GenerateEmbeddingsService

__all__ = [
    "SummarizedStageFacade",
    "SummaryResult",
    "EmbeddingResult",
    "GenerateSummaryService",
    "GenerateEmbeddingsService",
]
