"""Summarized Stage Facade - orchestrates document summarization and vector embeddings."""

from uuid import UUID
from app.core.base_stage import BaseStage, StageResult, StageStatus
from .services.generate_summary import GenerateSummaryService
from .services.generate_embeddings import GenerateEmbeddingsService


class SummarizedStageFacade(BaseStage):
    """
    Summarized stage: Human/system-facing outputs.
    
    Coordinates:
    - Document summarization
    - Vector embedding generation
    """
    
    def __init__(
        self,
        generate_summary: GenerateSummaryService,
        generate_embeddings: GenerateEmbeddingsService,
    ):
        self._generate_summary = generate_summary
        self._generate_embeddings = generate_embeddings
    
    @property
    def name(self) -> str:
        return "summarized"
    
    @property
    def dependencies(self) -> list[str]:
        return ["enriched"]
    
    async def is_complete(self, document_id: UUID) -> bool:
        """Check if summary/embeddings already exist."""
        # Implementation would check summary repository
        pass
    
    async def execute(self, document_id: UUID, *args, **kwargs) -> StageResult:
        """Execute the Summarized stage."""
        # 1. Generate summary
        summary_results = await self._generate_summary.execute(document_id)
        
        # 2. Generate embeddings
        embedding_results = await self._generate_embeddings.execute(document_id)
        
        return StageResult(
            status=StageStatus.COMPLETED,
            data={
                "summary_length": len(summary_results.summary_text),
                "chunks_embedded": embedding_results.chunks_embedded,
            }
        )
