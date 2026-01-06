"""Temporal workflows for document processing."""

from .process_document import ProcessDocumentWorkflow

# Import child workflows
from .child.page_analysis import PageAnalysisWorkflow
from .child.ocr_extraction import OCRExtractionWorkflow
from .child.table_extraction import TableExtractionWorkflow
from .child.hybrid_chunking import HybridChunkingWorkflow
from .child.extraction import ExtractionWorkflow
from .child.entity_resolution import EntityResolutionWorkflow

# Import stage workflows
from .stages.processed import ProcessedStageWorkflow
from .stages.extracted import ExtractedStageWorkflow
from .stages.enriched import EnrichedStageWorkflow
from .stages.summarized import SummarizedStageWorkflow

__all__ = [
    "ProcessDocumentWorkflow",
    "ProcessedStageWorkflow",
    "ExtractedStageWorkflow",
    "EnrichedStageWorkflow",
    "SummarizedStageWorkflow",
    "PageAnalysisWorkflow",
    "OCRExtractionWorkflow",
    "TableExtractionWorkflow",
    "HybridChunkingWorkflow",
    "ExtractionWorkflow",
    "EntityResolutionWorkflow",
]
