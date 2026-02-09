from app.schemas.query import ContextPayload, MergedResult

def format_context_for_llm(context: ContextPayload) -> str:
    """
    Format the context payload into a structured Markdown string for the LLM.
    
    Structure:
    # Full Text Sources
    [1] Document Name (Page X)
    Content...
    
    # Summarized Sources
    [N] Document Name (Section Y)
    Summary...
    """
    sections = []
    
    # Fallback counter if citation_id is not present on result object
    citation_counter = 1
    
    if context.full_text_results:
        sections.append("## High Priority Sources (Full Text)")
        for result in context.full_text_results:
            citation_label = getattr(result, "citation_id", None) or f"[{citation_counter}]"
            
            sections.append(
                f"### Source {citation_label}: {result.document_name} "
                f"(Pages: {', '.join(map(str, result.page_numbers)) if result.page_numbers else 'N/A'})\n"
                f"**Section**: {result.section_type or 'Unknown'}\n"
                f"{result.content}\n"
            )
            if not getattr(result, "citation_id", None):
                citation_counter += 1
            
    if context.summary_results:
        sections.append("## Additional Sources (Summaries)")
        for result in context.summary_results:
            citation_label = getattr(result, "citation_id", None) or f"[{citation_counter}]"
            
            sections.append(
                f"- **{citation_label}** {result.document_name}: {result.summary}\n"
                f"  *Section: {result.section_type}*"
            )
            if not getattr(result, "citation_id", None):
                citation_counter += 1
            
    if not sections:
        return "No relevant context found."
        
    return "\n\n".join(sections)
