from unittest.mock import MagicMock, AsyncMock, patch
import pytest
from uuid import uuid4

from app.services.extracted.services.extraction.section.section_extraction_orchestrator import SectionExtractionOrchestrator
from app.services.processed.services.chunking.hybrid_models import SectionSuperChunk, SectionType, HybridChunk, HybridChunkMetadata
from app.models.page_analysis_models import SemanticRole

class TestEndorsementRouting:
    """Test suite for extraction orchestrator routing logic."""
    
    @pytest.fixture
    def orchestrator(self):
        session = MagicMock()
        provider = MagicMock()
        
        # Initialize orchestrator
        # This will call _register_extractors, which we've fixed with imports
        orchestrator = SectionExtractionOrchestrator(session, provider)
        
        # Mock factory to return dummy extractors
        factory = MagicMock()
        factory.get_extractor.side_effect = lambda k: MagicMock(name=k)
        orchestrator.factory = factory
        
        # Mock _run_extraction_call to avoid needing complex extractor/client mocks
        orchestrator._run_extraction_call = AsyncMock(return_value={"extracted_data": []})
        
        return orchestrator
        
    @pytest.mark.asyncio
    async def test_route_both_to_provision(self, orchestrator):
        """Test that BOTH semantic role routes to provision extractor."""
        doc_id = uuid4()
        wf_id = uuid4()
        chunk = HybridChunk(
            text="text",
            metadata=HybridChunkMetadata(
                section_type=SectionType.ENDORSEMENTS,
                effective_section_type=SectionType.COVERAGES,
                semantic_role=SemanticRole.BOTH,
                token_count=100
            )
        )
        super_chunk = SectionSuperChunk(
            section_type=SectionType.ENDORSEMENTS,
            section_name="Endorsement",
            chunks=[chunk],
            document_id=doc_id
        )
        
        await orchestrator._extract_section(super_chunk, doc_id, wf_id)
        
        # Should have called get_extractor with "endorsement_provision"
        orchestrator.factory.get_extractor.assert_any_call("endorsement_provision")
        
    @pytest.mark.asyncio
    async def test_route_coverage_relaxed(self, orchestrator):
        """Test that coverage modifier routes to coverage projection even with weird effective type."""
        doc_id = uuid4()
        wf_id = uuid4()
        chunk = HybridChunk(
            text="text",
            metadata=HybridChunkMetadata(
                section_type=SectionType.ENDORSEMENTS,
                effective_section_type=SectionType.UNKNOWN,
                semantic_role=SemanticRole.COVERAGE_MODIFIER,
                token_count=100
            )
        )
        super_chunk = SectionSuperChunk(
            section_type=SectionType.ENDORSEMENTS,
            section_name="Endorsement",
            chunks=[chunk]
        )
        
        await orchestrator._extract_section(super_chunk, doc_id, wf_id)
        
        orchestrator.factory.get_extractor.assert_any_call("endorsement_coverage_projection")
        
    @pytest.mark.asyncio
    async def test_route_base_policy_standard(self, orchestrator):
        """Test that base policy sections still use standard routing."""
        doc_id = uuid4()
        wf_id = uuid4()
        chunk = HybridChunk(
            text="text",
            metadata=HybridChunkMetadata(
                section_type=SectionType.COVERAGES,
                effective_section_type=SectionType.COVERAGES,
                semantic_role=None,
                token_count=100
            )
        )
        super_chunk = SectionSuperChunk(
            section_type=SectionType.COVERAGES,
            section_name="Coverages",
            chunks=[chunk]
        )
        
        await orchestrator._extract_section(super_chunk, doc_id, wf_id)
        
        # For base coverages, it uses the enum value or registered type
        # The key should NOT be a projection extractor
        calls = [call[0][0] for call in orchestrator.factory.get_extractor.call_args_list]
        assert "endorsement_coverage_projection" not in calls
        assert "endorsement_provision" not in calls
