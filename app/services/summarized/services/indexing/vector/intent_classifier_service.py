from typing import List, Dict, Set
from app.services.summarized.constants import INTENT_RULES, INTENT_KEYWORD_MAP
from app.utils.logging import get_logger
LOGGER = get_logger(__name__)
class IntentClassifierService:
    """Lightweight rule-based intent classifier for insurance queries.
    
    This service determines which document sections are relevant to a given query
    to enable precise filtering of the semantic search space.
    """
    def __init__(self):
        # Intent mapping rules
        self.rules = INTENT_RULES
        self.keyword_map = INTENT_KEYWORD_MAP
    def classify(self, query: str) -> List[str]:
        """Classify a query into relevant section types.
        
        Args:
            query: The user query string.
            
        Returns:
            List of allowed section_type strings. If no intent is matched,
            returns an empty list (meaning no filter applied).
        """
        query_lower = query.lower()
        matched_intents: Set[str] = set()
        
        for keyword, intent in self.keyword_map.items():
            if keyword in query_lower:
                matched_intents.add(intent)
        
        allowed_sections: Set[str] = set()
        for intent in matched_intents:
            allowed_sections.update(self.rules[intent])
        
        result = list(allowed_sections)
        LOGGER.info(f"Classified query '{query}' into intents {matched_intents} -> sections {result}")
        return result