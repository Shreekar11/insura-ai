import pytest
import json
from uuid import uuid4
from unittest.mock import MagicMock

from app.services.normalization.normalization_service import NormalizationService
from app.services.normalization.llm_normalizer import LLMNormalizer

class TestSectionSeparation:
    
    def test_stable_chunk_id_generation(self):
        """Test deterministic generation of chunk IDs."""
        service = NormalizationService(use_hybrid=False)
        doc_id = uuid4()
        page_num = 5
        chunk_idx = 3
        
        expected_id = f"doc_{doc_id}_p{page_num}_c{chunk_idx}"
        actual_id = service._generate_stable_chunk_id(doc_id, page_num, chunk_idx)
        
        assert actual_id == expected_id
        
        # Verify stability
        assert service._generate_stable_chunk_id(doc_id, page_num, chunk_idx) == expected_id
        
    def test_llm_response_parsing_with_sections(self):
        """Test parsing of LLM response including section fields."""
        normalizer = LLMNormalizer(openrouter_api_key="dummy")
        
        # Mock response with section info
        llm_response = json.dumps({
            "normalized_text": "Normalized content",
            "section_type": "Declarations",
            "subsection_type": "Named Insured",
            "section_confidence": 0.95,
            "signals": {"policy": 0.9},
            "keywords": ["test"],
            "entities": {},
            "confidence": 0.8
        })
        
        parsed = normalizer._parse_signal_response(llm_response)
        
        assert parsed["normalized_text"] == "Normalized content"
        assert parsed["section_type"] == "Declarations"
        assert parsed["subsection_type"] == "Named Insured"
        assert parsed["section_confidence"] == 0.95
        assert parsed["signals"]["policy"] == 0.9
        
    def test_llm_response_parsing_missing_sections(self):
        """Test parsing of LLM response when section fields are missing (backward compatibility)."""
        normalizer = LLMNormalizer(openrouter_api_key="dummy")
        
        # Mock response without section info
        llm_response = json.dumps({
            "normalized_text": "Normalized content",
            "signals": {"policy": 0.9},
            "keywords": ["test"],
            "entities": {},
            "confidence": 0.8
        })
        
        parsed = normalizer._parse_signal_response(llm_response)
        
        assert parsed["normalized_text"] == "Normalized content"
        assert parsed["section_type"] is None
        assert parsed["subsection_type"] is None
        assert parsed["section_confidence"] == 0.0
