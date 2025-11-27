"""Tests for unified batch extractor.

This test suite validates the optimized batch processing pipeline that reduces
LLM calls by combining normalization, entity extraction, and section detection.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.services.extraction.unified_batch_extractor import UnifiedBatchExtractor
from app.utils.exceptions import APIClientError


class TestUnifiedBatchExtractor:
    """Test suite for UnifiedBatchExtractor."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        return session
    
    @pytest.fixture
    def sample_chunks(self):
        """Create sample chunks for testing."""
        return [
            {
                "chunk_id": "ch_001",
                "text": "POLICY NUMBER: ABC-123-456\nEFFECTIVE DATE: 01/15/2024\nCARRIER: Acme Insurance Co.\nPREMIUM: $5,500.00"
            },
            {
                "chunk_id": "ch_002",
                "text": "COVERAGE A - BUILDING: Limit $5,000,000, Deductible $5,000"
            },
            {
                "chunk_id": "ch_003",
                "text": "EXCLUSIONS: We do not cover wear and tear or intentional damage"
            }
        ]
    
    @pytest.fixture
    def sample_llm_response(self):
        """Create sample LLM response."""
        return {
            "results": {
                "ch_001": {
                    "normalized_text": "POLICY NUMBER: ABC-123-456\nEFFECTIVE DATE: 2024-01-15\nCARRIER: Acme Insurance Co.\nPREMIUM: 5500.00 USD",
                    "entities": [
                        {
                            "entity_type": "POLICY_NUMBER",
                            "raw_value": "ABC-123-456",
                            "normalized_value": "ABC-123-456",
                            "confidence": 0.98,
                            "span_start": 15,
                            "span_end": 26
                        },
                        {
                            "entity_type": "EFFECTIVE_DATE",
                            "raw_value": "01/15/2024",
                            "normalized_value": "2024-01-15",
                            "confidence": 0.95,
                            "span_start": 43,
                            "span_end": 53
                        }
                    ],
                    "section_type": "declarations",
                    "signals": {
                        "policy": 0.95,
                        "claim": 0.05,
                        "submission": 0.0,
                        "quote": 0.0,
                        "proposal": 0.0,
                        "SOV": 0.0,
                        "financials": 0.0,
                        "loss_run": 0.0,
                        "audit": 0.0,
                        "endorsement": 0.05,
                        "invoice": 0.10,
                        "correspondence": 0.0,
                    }
                },
                "ch_002": {
                    "normalized_text": "COVERAGE A - BUILDING: Limit 5000000.00 USD, Deductible 5000.00 USD",
                    "entities": [
                        {
                            "entity_type": "COVERAGE_LIMIT",
                            "raw_value": "$5,000,000",
                            "normalized_value": "5000000.00 USD",
                            "confidence": 0.97,
                            "span_start": 29,
                            "span_end": 39
                        }
                    ],
                    "section_type": "coverages",
                    "signals": {
                        "policy": 0.90,
                        "claim": 0.05,
                        "submission": 0.0,
                        "quote": 0.0,
                        "proposal": 0.0,
                        "SOV": 0.0,
                        "financials": 0.0,
                        "loss_run": 0.0,
                        "audit": 0.0,
                        "endorsement": 0.05,
                        "invoice": 0.05,
                        "correspondence": 0.0,
                    }
                },
                "ch_003": {
                    "normalized_text": "EXCLUSIONS: We do not cover wear and tear or intentional damage",
                    "entities": [],
                    "section_type": "exclusions",
                    "signals": {
                        "policy": 0.85,
                        "claim": 0.05,
                        "submission": 0.0,
                        "quote": 0.0,
                        "proposal": 0.0,
                        "SOV": 0.0,
                        "financials": 0.0,
                        "loss_run": 0.0,
                        "audit": 0.0,
                        "endorsement": 0.05,
                        "invoice": 0.05,
                        "correspondence": 0.0,
                    }
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_extract_batch_success(
        self,
        mock_session,
        sample_chunks,
        sample_llm_response
    ):
        """Test successful batch extraction."""
        # Setup
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key",
            batch_size=3
        )
        
        # Mock LLM API call
        with patch.object(extractor, '_call_llm_api', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = sample_llm_response["results"]
            
            # Execute
            document_id = uuid4()
            results = await extractor.extract_batch(sample_chunks, document_id)
            
            # Assert
            assert len(results) == 3
            assert "ch_001" in results
            assert "ch_002" in results
            assert "ch_003" in results
            
            # Verify chunk 1 results
            ch1 = results["ch_001"]
            assert "normalized_text" in ch1
            assert "entities" in ch1
            assert "section_type" in ch1
            assert ch1["section_type"] == "declarations"
            assert len(ch1["entities"]) == 2
            
            # Verify entity extraction
            policy_entity = ch1["entities"][0]
            assert policy_entity["entity_type"] == "POLICY_NUMBER"
            assert policy_entity["normalized_value"] == "ABC-123-456"
            assert policy_entity["confidence"] == 0.98
    
    @pytest.mark.asyncio
    async def test_extract_batch_empty_chunks(self, mock_session):
        """Test batch extraction with empty chunks list."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        document_id = uuid4()
        
        with pytest.raises(ValueError, match="Chunks list cannot be empty"):
            await extractor.extract_batch([], document_id)
    
    @pytest.mark.asyncio
    async def test_extract_batch_partial_failure(
        self,
        mock_session,
        sample_chunks
    ):
        """Test batch extraction with partial failures."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        # Mock LLM response missing one chunk
        partial_response = {
            "ch_001": {
                "normalized_text": "text",
                "entities": [],
                "section_type": "unknown",
                "signals": {}
            },
            "ch_002": {
                "normalized_text": "text",
                "entities": [],
                "section_type": "unknown",
                "signals": {}
            }
            # ch_003 is missing!
        }
        
        # Mock fallback processing
        fallback_response = {
            "ch_003": {
                "normalized_text": "fallback text",
                "entities": [],
                "section_type": "unknown",
                "signals": {}
            }
        }
        
        with patch.object(extractor, '_call_llm_api', new_callable=AsyncMock) as mock_llm:
            # First call returns partial results, second call (fallback) returns missing chunk
            mock_llm.side_effect = [partial_response, fallback_response]
            
            document_id = uuid4()
            results = await extractor.extract_batch(sample_chunks, document_id)
            
            # Assert all chunks processed (including fallback)
            assert len(results) == 3
            assert "ch_001" in results
            assert "ch_002" in results
            assert "ch_003" in results
            
            # Verify fallback was called
            assert mock_llm.call_count == 2
    
    @pytest.mark.asyncio
    async def test_extract_batch_api_error(self, mock_session, sample_chunks):
        """Test batch extraction with API error."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        with patch.object(extractor, '_call_llm_api', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = APIClientError("API call failed")
            
            document_id = uuid4()
            
            with pytest.raises(APIClientError):
                await extractor.extract_batch(sample_chunks, document_id)
    
    def test_parse_response_valid_json(self, mock_session):
        """Test parsing valid JSON response."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        response_text = '{"results": {"ch_001": {"normalized_text": "test"}}}'
        parsed = extractor._parse_response(response_text)
        
        assert "results" in parsed
        assert "ch_001" in parsed["results"]
    
    def test_parse_response_invalid_json(self, mock_session):
        """Test parsing invalid JSON response."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        response_text = "invalid json {{"
        parsed = extractor._parse_response(response_text)
        
        # Should return empty results on parse failure
        assert parsed == {"results": {}}
    
    @pytest.mark.asyncio
    async def test_batch_size_configuration(self, mock_session):
        """Test batch size configuration."""
        # Test with custom batch size
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key",
            batch_size=5
        )
        
        assert extractor.batch_size == 5
    
    @pytest.mark.asyncio
    async def test_entity_normalization(
        self,
        mock_session,
        sample_chunks,
        sample_llm_response
    ):
        """Test that entities are properly normalized."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        with patch.object(extractor, '_call_llm_api', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = sample_llm_response["results"]
            
            document_id = uuid4()
            results = await extractor.extract_batch(sample_chunks, document_id)
            
            # Verify date normalization
            ch1 = results["ch_001"]
            date_entity = next(
                e for e in ch1["entities"] 
                if e["entity_type"] == "EFFECTIVE_DATE"
            )
            assert date_entity["normalized_value"] == "2024-01-15"
            assert date_entity["raw_value"] == "01/15/2024"
            
            # Verify currency normalization
            ch2 = results["ch_002"]
            amount_entity = ch2["entities"][0]
            assert "USD" in amount_entity["normalized_value"]
    
    @pytest.mark.asyncio
    async def test_section_type_detection(
        self,
        mock_session,
        sample_chunks,
        sample_llm_response
    ):
        """Test section type detection."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        with patch.object(extractor, '_call_llm_api', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = sample_llm_response["results"]
            
            document_id = uuid4()
            results = await extractor.extract_batch(sample_chunks, document_id)
            
            # Verify section types
            assert results["ch_001"]["section_type"] == "declarations"
            assert results["ch_002"]["section_type"] == "coverages"
            assert results["ch_003"]["section_type"] == "exclusions"
    
    @pytest.mark.asyncio
    async def test_classification_signals(
        self,
        mock_session,
        sample_chunks,
        sample_llm_response
    ):
        """Test classification signal extraction."""
        extractor = UnifiedBatchExtractor(
            session=mock_session,
            gemini_api_key="test-key"
        )
        
        with patch.object(extractor, '_call_llm_api', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = sample_llm_response["results"]
            
            document_id = uuid4()
            results = await extractor.extract_batch(sample_chunks, document_id)
            
            # Verify signals
            ch1_signals = results["ch_001"]["signals"]
            assert ch1_signals["policy"] == 0.95
            assert ch1_signals["claim"] == 0.05
            assert all(0.0 <= v <= 1.0 for v in ch1_signals.values())
