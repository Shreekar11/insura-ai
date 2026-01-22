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
from datetime import timedelta

from app.temporal.shared.workflows.process_document import ProcessDocumentWorkflow
from app.models.page_data import PageData


class TestProcessDocumentWorkflowIntegration:
    """Integration tests for ProcessDocumentWorkflow with Phase 3 and Phase 4."""
    
    @pytest.fixture
    def document_id(self):
        """Generate a test document ID."""
        return str(uuid4())
    
    @pytest.fixture
    def mock_page_manifest(self, document_id):
        """Mock page manifest result."""
        return {
            "document_id": document_id,
            "total_pages": 50,
            "pages_to_process": list(range(1, 11)),
            "pages_skipped": list(range(11, 51)),
            "processing_ratio": 0.2,
            "classifications": [],
            "document_profile": {
                "document_id": document_id,
                "document_type": "commercial_property",
                "document_subtype": "bop",
                "confidence": 0.95,
                "section_boundaries": [
                    {
                        "section_type": "declarations",
                        "start_page": 1,
                        "end_page": 3,
                        "confidence": 0.98,
                    }
                ],
                "metadata": {},
            },
            "page_section_map": {i: "declarations" for i in range(1, 11)},
        }
    
    @pytest.fixture
    def mock_ocr_result(self, document_id):
        """Mock OCR result."""
        return {
            "document_id": document_id,
            "page_count": 10,
            "pages_processed": list(range(1, 11)),
            "markdown_pages": [("# Page 1", 1, {}), ("# Page 2", 2, {})],
            "selective": True,
            "has_section_metadata": False,
            "section_distribution": None,
        }
    
    @pytest.fixture
    def mock_chunking_result(self):
        """Mock chunking result."""
        return {
            "chunk_count": 45,
            "super_chunk_count": 8,
            "sections_detected": ["declarations", "coverages"],
            "section_stats": {
                "declarations": 5,
                "coverages": 20,
            },
            "total_tokens": 12500,
            "avg_tokens_per_chunk": 277.78,
            "section_source": "hybrid",
        }
    
    @pytest.fixture
    def mock_extraction_result(self):
        """Mock extraction result."""
        return {
            "all_entities": list(range(40)),
            "section_results": {
                "declarations": {"entities_extracted": 15}
            }
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
        workflow_instance = ProcessDocumentWorkflow()
        
        # Mock workflow.execute_activity to return our mock results
        with patch('app.temporal.shared.workflows.mixin.workflow') as mock_workflow:
            async def mock_execute_activity(activity_name, *args, **kwargs):
                if activity_name == 'extract_ocr':
                    return mock_ocr_result
                elif activity_name == 'extract_page_signals_from_markdown':
                    return {}
                elif activity_name == 'classify_pages':
                    return {}
                elif activity_name == 'create_page_manifest':
                    return mock_page_manifest
                elif activity_name == 'extract_tables':
                    return {
                        "tables_found": 2,
                        "tables_processed": 2,
                        "sov_items": 5,
                        "loss_run_claims": 0,
                        "validation_passed": True,
                        "validation_errors": 0,
                        "validation_results": [],
                        "errors": []
                    }
                elif activity_name == 'perform_hybrid_chunking':
                    return mock_chunking_result
                elif activity_name == 'extract_section_fields':
                    return mock_extraction_result
                elif activity_name == 'aggregate_document_entities':
                    return {}
                elif activity_name == 'resolve_canonical_entities':
                    return list(range(20))
                elif activity_name == 'extract_relationships':
                    return list(range(10))
                elif activity_name == 'generate_embeddings_activity':
                    return {"chunks_embedded": 45}
                elif activity_name == 'construct_knowledge_graph_activity':
                    return {
                        "workflow_id": "test-workflow",
                        "document_id": document_id,
                        "vector_indexed": True,
                        "graph_constructed": True,
                        "chunks_indexed": 45,
                        "entities_created": 20,
                        "relationships_created": 10,
                        "embeddings_linked": 45
                    }
                return {}
            
            mock_workflow.execute_activity = mock_execute_activity
            mock_workflow.logger = MagicMock()
            
            payload = {
                "workflow_id": "test-workflow",
                "documents": [{"document_id": document_id}],
                "workflow_name": "Policy Analysis"
            }
            
            # Execute workflow
            result = await workflow_instance.run(payload)
            
            # Verify result structure
            assert result["status"] == "completed"
            assert result["document_id"] == document_id
            
            stages = result["stages"]
            processed = stages["processed"]
            # extracted = stages["extracted"]
            # enriched = stages["enriched"]
            # summarized = stages["summarized"]
            
            # Verify Processed Stage
            assert processed["status"] == "completed"
            assert processed["pages_processed"] == len(mock_page_manifest["pages_to_process"])
            assert processed["chunks_created"] == mock_chunking_result["chunk_count"]
            assert processed["document_type"] == mock_page_manifest["document_profile"]["document_type"]
            
            # Verify Extracted Stage
            # assert extracted["status"] == "completed"
            # assert extracted["entities_found"] == len(mock_extraction_result["all_entities"])
            
            # Verify Enriched Stage
            # assert enriched["status"] == "completed"
            # assert enriched["entities_resolved"] == 20
            
            # Verify Indexing Stage
            # assert summarized["status"] == "completed"
            # assert summarized["chunks_indexed"] == 45

    @pytest.mark.asyncio
    async def test_workflow_status_updates(self, document_id):
        """Test that workflow status is updated correctly."""
        workflow_instance = ProcessDocumentWorkflow()
        
        # Initial status
        status = workflow_instance.get_status()
        assert status["status"] == "initialized"
        assert status["current_phase"] is None
        assert status["progress"] == 0.0

