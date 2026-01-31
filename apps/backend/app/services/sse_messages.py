from typing import Dict, Optional

def format_stage_message(stage_name: str, status: str, metadata: Optional[Dict] = None) -> str:
    """Format a human-readable message for a processing stage."""
    metadata = metadata or {}
    
    templates = {
        "processed": {
            "running": "Processing {document_name}",
            "completed": "Processed {document_name}",
            "failed": "Failed to process {document_name}"
        },
        "classified": {
            "running": "Classifying {document_name}",
            "completed": "Classified {document_name} as {document_type}",
            "failed": "Failed to classify {document_name}"
        },
        "extracted": {
            "running": "Extracting sections from {document_name}",
            "completed": "Extracted {section_count} sections from {document_name}",
            "failed": "Failed to extract data from {document_name}"
        },
        "enriched": {
            "running": "Enriching {document_name}",
            "completed": "Enriched {document_name}",
            "failed": "Failed to enrich data."
        },
        "summarized": {
            "running": "Building knowledge base",
            "completed": "Knowledge base ready",
            "failed": "Failed to build knowledge base."
        }
    }
    
    if stage_name not in templates:
        return f"Stage {stage_name} is {status}"
        
    template = templates[stage_name].get(status, f"{stage_name.capitalize()} stage {status}")
    
    try:
        # Specialized formatting for classification
        if stage_name == "classified" and status == "completed":
            doc_type = metadata.get("document_profile", {}).get("document_type", "unknown")
            return template.replace("{document_name}", str(metadata.get("document_name", "document"))) \
                           .replace("{document_type}", str(doc_type))
            
        return template.format(**metadata)
    except Exception:
        return template
