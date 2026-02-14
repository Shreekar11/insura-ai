from app.schemas.query import ContextPayload, MergedResult

def format_context_for_llm(context: ContextPayload) -> str:
    """
    Format the context payload into a structured Markdown string for the LLM.
    
    Structure:
    # Full Text Sources
    Document Name (Page X)
    Content...
    
    # Summarized Sources
    Document Name (Section Y)
    Summary...
    """
    sections = []
    
    if context.full_text_results:
        sections.append("## High Priority Sources (Full Text)")
        for result in context.full_text_results:
            sections.append(
                f"### Source: {result.document_name} "
                f"(Pages: {', '.join(map(str, result.page_numbers)) if result.page_numbers else 'N/A'})\n"
                f"**Section**: {result.section_type or 'Unknown'}\n"
                f"{result.content}\n"
            )
            
    if context.summary_results:
        sections.append("## Additional Sources (Summaries)")
        for result in context.summary_results:
            sections.append(
                f"- **{result.document_name}**: {result.summary}\n"
                f"  *Section: {result.section_type}*"
            )
                
    # New Section: Relationship Context
    rel_context = []
    seen_quotes = set()
    
    # Collect all graph results that have relationship chains or evidence quotes
    all_results = (context.full_text_results or []) + (context.summary_results or [])
    for res in all_results:
        if res.relationship_path:
            path_str = " → ".join(res.relationship_path)
            rel_line = f"- Relationship: {path_str}"
            
            # Add evidence quotes if present
            if hasattr(res, 'evidence_quotes') and res.evidence_quotes:
                quotes = []
                for q in res.evidence_quotes:
                    if q not in seen_quotes:
                        quotes.append(f"  > \"{q.strip()}\"")
                        seen_quotes.add(q)
                if quotes:
                    rel_line += "\n" + "\n".join(quotes)
            
            rel_context.append(rel_line)

    if rel_context:
        sections.append("## Relational Evidence (Graph-Derived)")
        sections.extend(rel_context)
            
    if not sections:
        return "No relevant context found."
        
    return "\n\n".join(sections)
