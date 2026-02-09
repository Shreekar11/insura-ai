import re
from typing import List, Set

from app.schemas.query import GeneratedResponse, FormattedResponse, SourceCitation
from app.utils.logging import get_logger

LOGGER = get_logger(__name__)

class CitationFormatterService:
    """
    Service for extracting citations from LLM text and formatting them into structured data.
    """

    def __init__(self):
        self.citation_pattern = re.compile(r"\[(\d+)\]")

    def format_response(self, generated: GeneratedResponse) -> FormattedResponse:
        """
        Extract citations from the answer and attach provenance data.
        """
        answer = generated.answer
        provenance_map = generated.provenance
        
        # Find all unique citation numbers in the text
        matches = self.citation_pattern.findall(answer)
        unique_ids: Set[str] = set(matches)
        
        sources: List[SourceCitation] = []
        
        for num in sorted(unique_ids, key=int):
            citation_key = f"[{num}]"
            
            if citation_key in provenance_map:
                entry = provenance_map[citation_key]
                
                # Format relationship context string
                rel_context = None
                if entry.relationship_path:
                    rel_context = f"Related via: {' → '.join(entry.relationship_path)}"
                
                sources.append(SourceCitation(
                    citation_id=num,
                    document_name=entry.document_name,
                    document_id=entry.document_id,
                    page_numbers=entry.page_numbers,
                    section_type=entry.section_type or "Unknown",
                    relationship_context=rel_context
                ))
            else:
                LOGGER.warning(f"LLM cited {citation_key} but it was not in the provenance index.")

        return FormattedResponse(
            answer=answer,
            sources=sources
        )
