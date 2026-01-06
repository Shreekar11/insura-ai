"""Unit tests for extraction services.

Tests the extraction LLM processing:
- DocumentClassificationService
- SectionExtractionOrchestrator
- CrossSectionValidator
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import json

from app.services.extraction.section_extraction_orchestrator import (
    SectionExtractionOrchestrator,
    SectionExtractionResult,
    DocumentExtractionResult,
)
from app.services.chunking.hybrid_models import SectionType, SectionSuperChunk, HybridChunk, HybridChunkMetadata

class TestSectionExtractionOrchestrator:
    """Test suite for Tier 2 SectionExtractionOrchestrator."""
    
    @pytest.fixture
    def mock_extraction_response(self):
        """Create mock LLM extraction response."""
        return json.dumps({
            "fields": {
                "policy_number": "POL-2024-001",
                "insured_name": "ABC Manufacturing LLC",
                "effective_date": "2024-01-01",
            },
            "entities": [
                {"type": "POLICY_NUMBER", "value": "POL-2024-001", "confidence": 0.95},
                {"type": "INSURED_NAME", "value": "ABC Manufacturing LLC", "confidence": 0.92},
            ],
            "confidence": 0.90
        })
    
    @pytest.fixture
    def orchestrator(self, mock_extraction_response):
        """Create orchestrator with mocked LLM client."""
        with patch('app.services.extraction.section_extraction_orchestrator.UnifiedLLMClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.generate_content = AsyncMock(return_value=mock_extraction_response)
            MockClient.return_value = mock_client
            
            orchestrator = SectionExtractionOrchestrator(
                provider="gemini",
                gemini_api_key="test-key",
            )
            orchestrator.client = mock_client
            return orchestrator
    
    @pytest.fixture
    def sample_super_chunks(self):
        """Create sample super-chunks for testing."""
        document_id = uuid4()
        
        return [
            SectionSuperChunk(
                section_type=SectionType.DECLARATIONS,
                section_name="Declarations",
                chunks=[
                    HybridChunk(
                        text="Policy Number: POL-2024-001\nInsured: ABC Manufacturing",
                        metadata=HybridChunkMetadata(
                            document_id=document_id,
                            section_type=SectionType.DECLARATIONS,
                            token_count=100,
                        ),
                    )
                ],
                document_id=document_id,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.COVERAGES,
                section_name="Coverages",
                chunks=[
                    HybridChunk(
                        text="Coverage A - Building: $5,000,000",
                        metadata=HybridChunkMetadata(
                            document_id=document_id,
                            section_type=SectionType.COVERAGES,
                            token_count=80,
                        ),
                    )
                ],
                document_id=document_id,
                requires_llm=True,
            ),
            SectionSuperChunk(
                section_type=SectionType.SOV,
                section_name="SOV",
                chunks=[],
                document_id=document_id,
                requires_llm=False,
                table_only=True,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_extract_all_sections(self, orchestrator, sample_super_chunks):
        """Test extracting all sections."""
        result = await orchestrator.extract_all_sections(sample_super_chunks)
        
        assert isinstance(result, DocumentExtractionResult)
        # Should only extract LLM-required sections
        assert len(result.section_results) == 2
    
    @pytest.mark.asyncio
    async def test_extract_section_result_structure(self, orchestrator, sample_super_chunks):
        """Test structure of section extraction results."""
        result = await orchestrator.extract_all_sections(sample_super_chunks)
        
        for section_result in result.section_results:
            assert isinstance(section_result, SectionExtractionResult)
            assert section_result.section_type is not None
            assert isinstance(section_result.extracted_data, dict)
            assert isinstance(section_result.entities, list)
    
    @pytest.mark.asyncio
    async def test_extract_entities_aggregated(self, orchestrator, sample_super_chunks):
        """Test that entities are aggregated across sections."""
        result = await orchestrator.extract_all_sections(sample_super_chunks)
        
        assert len(result.all_entities) > 0
    
    @pytest.mark.asyncio
    async def test_extract_empty_super_chunks(self, orchestrator):
        """Test extraction with empty super-chunks."""
        result = await orchestrator.extract_all_sections([])
        
        assert len(result.section_results) == 0
        assert result.total_tokens == 0
    
    @pytest.mark.asyncio
    async def test_get_section_result(self, orchestrator, sample_super_chunks):
        """Test getting result for specific section."""
        result = await orchestrator.extract_all_sections(sample_super_chunks)
        
        decl_result = result.get_section_result(SectionType.DECLARATIONS)
        assert decl_result is not None
        assert decl_result.section_type == SectionType.DECLARATIONS

