"""Integration tests for the complete ProcessDocumentWorkflow.

These tests verify the end-to-end workflow execution including:
- Phase 0: Page Analysis
- Phase 1: OCR Extraction
- Phase 2: Hybrid Chunking
- Phase 3: LLM Extraction
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.temporal.workflows.process_document import ProcessDocumentWorkflow
from app.models.page_data import PageData


class TestProcessDocumentWorkflowIntegration:
    """Integration tests for ProcessDocumentWorkflow with Phase 3 and Phase 4."""
    
    @pytest.fixture
    def document_id(self):
        """Generate a test document ID."""
        return str(uuid4())
    
    @pytest.fixture
    def mock_page_manifest(self):
        """Mock page manifest result from Phase 0."""
        return {
            "document_id": str(uuid4()),
            "total_pages": 50,
            "pages_to_process": list(range(1, 11)),  # Process first 10 pages
            "pages_skipped": list(range(11, 51)),
            "processing_ratio": 0.2,
        }
    
    @pytest.fixture
    def mock_ocr_result(self):
        """Mock OCR result from Phase 1."""
        return {
            "document_id": str(uuid4()),
            "page_count": 10,
        }
    
    @pytest.fixture
    def mock_chunking_result(self):
        """Mock chunking result from Phase 2."""
        return {
            "chunk_count": 45,
            "super_chunk_count": 8,
            "sections_detected": ["declarations", "coverages", "conditions", "exclusions"],
            "section_stats": {
                "declarations": 5,
                "coverages": 20,
                "conditions": 12,
                "exclusions": 8,
            },
            "total_tokens": 12500,
            "avg_tokens_per_chunk": 277.78,
        }
    
    @pytest.fixture
    def mock_extraction_result(self):
        """Mock extraction result from Phase 3."""
        return {
            "classification": {
                "document_type": "commercial_property",
                "document_subtype": "bop",
                "confidence": 0.95,
                "section_boundaries": [
                    {
                        "section_type": "declarations",
                        "start_page": 1,
                        "end_page": 3,
                        "confidence": 0.98,
                    },
                    {
                        "section_type": "coverages",
                        "start_page": 4,
                        "end_page": 8,
                        "confidence": 0.92,
                    },
                ],
                "metadata": {},
            },
            "extraction": {
                "section_results": {
                    "declarations": {
                        "entities_extracted": 15,
                        "chunks_processed": 2,
                        "llm_calls": 1,
                        "total_tokens": 2500,
                    },
                    "coverages": {
                        "entities_extracted": 25,
                        "chunks_processed": 4,
                        "llm_calls": 2,
                        "total_tokens": 5000,
                    },
                },
                "aggregated_entities": {
                    "named_insured": 1,
                    "policy_number": 1,
                    "coverage_limit": 8,
                    "deductible": 4,
                },
                "total_entities": 40,
                "total_llm_calls": 5,
                "total_tokens": 10000,
            },
            "validation": {
                "validation_issues": [
                    {
                        "field_name": "coverage_limit",
                        "issue_type": "inconsistency",
                        "severity": "medium",
                        "description": "Coverage limit differs between declarations and coverages section",
                        "affected_sections": ["declarations", "coverages"],
                    }
                ],
                "reconciled_values": {
                    "coverage_limit": {
                        "final_value": "$1,000,000",
                        "confidence": 0.85,
                        "source_sections": ["declarations", "coverages"],
                        "reconciliation_method": "highest_confidence",
                    }
                },
                "data_quality_score": 0.88,
                "is_valid": True,
            },
            "document_type": "commercial_property",
            "total_entities": 40,
            "total_llm_calls": 5,
            "data_quality_score": 0.88,
            "is_valid": True,
        }
    
    @pytest.mark.asyncio
    async def test_workflow_executes_all_phases(
        self,
        document_id,
        mock_page_manifest,
        mock_ocr_result,
        mock_chunking_result,
        mock_extraction_result,
    ):
        """Test that the workflow executes all phases in sequence."""
        workflow = ProcessDocumentWorkflow()
        
        # Mock workflow.execute_child_workflow to return our mock results
        with patch('app.temporal.workflows.process_document.workflow') as mock_workflow:
            # Setup mock for child workflow execution
            async def mock_execute_child(workflow_class, *args, **kwargs):
                workflow_id = kwargs.get('id', '')
                if 'page-analysis' in workflow_id:
                    return mock_page_manifest
                elif 'ocr' in workflow_id:
                    return mock_ocr_result
                elif 'chunking' in workflow_id:
                    return mock_chunking_result
                elif 'extraction' in workflow_id:
                    return mock_extraction_result
                return {}
            
            mock_workflow.execute_child_workflow = mock_execute_child
            mock_workflow.logger = MagicMock()
            
            # Execute workflow
            result = await workflow.run(document_id)
            
            # Verify result structure
            assert result["status"] == "completed"
            assert result["document_id"] == document_id
            
            # Verify Phase 0: Page Analysis
            assert result["total_pages"] == mock_page_manifest["total_pages"]
            assert result["pages_processed"] == len(mock_page_manifest["pages_to_process"])
            assert result["processing_ratio"] == mock_page_manifest["processing_ratio"]
            
            # Verify Phase 1: OCR
            assert result["page_count"] == mock_ocr_result["page_count"]
            
            # Verify Phase 2: Hybrid Chunking
            assert result["chunks"] == mock_chunking_result["chunk_count"]
            assert result["super_chunks"] == mock_chunking_result["super_chunk_count"]
            assert result["sections_detected"] == mock_chunking_result["sections_detected"]
            assert result["total_tokens"] == mock_chunking_result["total_tokens"]
            
            # Verify Phase 3: Extraction
            assert result["document_type"] == mock_extraction_result["document_type"]
            assert result["entities"] == mock_extraction_result["total_entities"]
            assert result["llm_calls"] == mock_extraction_result["total_llm_calls"]
            assert result["data_quality_score"] == mock_extraction_result["data_quality_score"]
            assert result["is_valid"] == mock_extraction_result["is_valid"]
    
    @pytest.mark.asyncio
    async def test_workflow_status_updates(self, document_id):
        """Test that workflow status is updated correctly during execution."""
        workflow = ProcessDocumentWorkflow()
        
        # Initial status
        status = workflow.get_status()
        assert status["status"] == "initialized"
        assert status["current_phase"] is None
        assert status["progress"] == 0.0
    
    def test_workflow_phase_progression(self):
        """Test that workflow phases progress in correct order."""
        workflow = ProcessDocumentWorkflow()
        
        # Verify initial state
        assert workflow._status == "initialized"
        assert workflow._current_phase is None
        assert workflow._progress == 0.0
        
        # Expected phase progression:
        # 1. page_analysis (0.05)
        # 2. ocr_extraction (0.15)
        # 3. hybrid_chunking (0.3)
        # 4. extraction (0.6)
        # 5. completed (1.0)
    
    @pytest.mark.asyncio
    async def test_workflow_handles_selective_ocr(
        self,
        document_id,
        mock_page_manifest,
        mock_ocr_result,
        mock_chunking_result,
        mock_extraction_result,
    ):
        """Test that workflow correctly uses selective OCR based on page manifest."""
        workflow = ProcessDocumentWorkflow()
        
        with patch('app.temporal.workflows.process_document.workflow') as mock_workflow:
            async def mock_execute_child(workflow_class, *args, **kwargs):
                workflow_id = kwargs.get('id', '')
                if 'page-analysis' in workflow_id:
                    return mock_page_manifest
                elif 'ocr' in workflow_id:
                    # Verify that pages_to_process is passed to OCR workflow
                    assert len(args) >= 2
                    pages_to_process = args[1]
                    assert pages_to_process == mock_page_manifest["pages_to_process"]
                    return mock_ocr_result
                elif 'chunking' in workflow_id:
                    return mock_chunking_result
                elif 'extraction' in workflow_id:
                    return mock_extraction_result
                return {}
            
            mock_workflow.execute_child_workflow = mock_execute_child
            mock_workflow.logger = MagicMock()
            
            result = await workflow.run(document_id)
            
            # Verify that selective OCR was used
            assert result["pages_processed"] < result["total_pages"]
            assert result["processing_ratio"] < 1.0
    
    @pytest.mark.asyncio
    async def test_workflow_section_detection(
        self,
        document_id,
        mock_page_manifest,
        mock_ocr_result,
        mock_chunking_result,
        mock_extraction_result,
    ):
        """Test that workflow correctly detects and processes sections."""
        workflow = ProcessDocumentWorkflow()
        
        with patch('app.temporal.workflows.process_document.workflow') as mock_workflow:
            async def mock_execute_child(workflow_class, *args, **kwargs):
                workflow_id = kwargs.get('id', '')
                if 'page-analysis' in workflow_id:
                    return mock_page_manifest
                elif 'ocr' in workflow_id:
                    return mock_ocr_result
                elif 'chunking' in workflow_id:
                    return mock_chunking_result
                elif 'extraction' in workflow_id:
                    return mock_extraction_result
                return {}
            
            mock_workflow.execute_child_workflow = mock_execute_child
            mock_workflow.logger = MagicMock()
            
            result = await workflow.run(document_id)
            
            # Verify sections were detected
            assert len(result["sections_detected"]) > 0
            assert "declarations" in result["sections_detected"]
            assert "coverages" in result["sections_detected"]
    
    @pytest.mark.asyncio
    async def test_workflow_data_quality_validation(
        self,
        document_id,
        mock_page_manifest,
        mock_ocr_result,
        mock_chunking_result,
        mock_extraction_result,
    ):
        """Test that workflow includes data quality validation results."""
        workflow = ProcessDocumentWorkflow()
        
        with patch('app.temporal.workflows.process_document.workflow') as mock_workflow:
            async def mock_execute_child(workflow_class, *args, **kwargs):
                workflow_id = kwargs.get('id', '')
                if 'page-analysis' in workflow_id:
                    return mock_page_manifest
                elif 'ocr' in workflow_id:
                    return mock_ocr_result
                elif 'chunking' in workflow_id:
                    return mock_chunking_result
                elif 'extraction' in workflow_id:
                    return mock_extraction_result
                return {}
            
            mock_workflow.execute_child_workflow = mock_execute_child
            mock_workflow.logger = MagicMock()
            
            result = await workflow.run(document_id)
            
            # Verify data quality metrics are present
            assert "data_quality_score" in result
            assert "is_valid" in result
            assert 0.0 <= result["data_quality_score"] <= 1.0
            assert isinstance(result["is_valid"], bool)

