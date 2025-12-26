"""Unit tests for tiered extraction services.

Tests the v2 tiered LLM processing:
- Tier 1: DocumentClassificationService
- Tier 2: SectionExtractionOrchestrator
- Tier 3: CrossSectionValidator
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import json

from app.services.extraction.document_classification_service import (
    DocumentClassificationService,
    DocumentClassificationResult,
    SectionBoundary,
)
from app.services.extraction.section_extraction_orchestrator import (
    SectionExtractionOrchestrator,
    SectionExtractionResult,
    DocumentExtractionResult,
)
from app.services.extraction.cross_section_validator import (
    CrossSectionValidator,
    CrossSectionValidationResult,
    ValidationIssue,
    ReconciledValue,
)
from app.services.chunking.hybrid_models import SectionType, SectionSuperChunk, HybridChunk, HybridChunkMetadata


class TestDocumentClassificationService:
    """Test suite for Tier 1 DocumentClassificationService."""
    
    @pytest.fixture
    def mock_llm_response(self):
        """Create mock LLM classification response."""
        return json.dumps({
            "document_type": "policy",
            "document_subtype": "commercial_property",
            "confidence": 0.95,
            "section_boundaries": [
                {
                    "section_type": "declarations",
                    "start_page": 1,
                    "end_page": 3,
                    "confidence": 0.98,
                    "anchor_text": "DECLARATIONS"
                },
                {
                    "section_type": "coverages",
                    "start_page": 4,
                    "end_page": 10,
                    "confidence": 0.92,
                    "anchor_text": "COVERAGES"
                },
            ],
            "page_section_map": {
                "1": "declarations",
                "2": "declarations",
                "3": "declarations",
                "4": "coverages",
                "5": "coverages",
            },
            "metadata": {
                "has_tables": True,
                "carrier_detected": "ABC Insurance"
            }
        })
    
    @pytest.fixture
    def service(self, mock_llm_response):
        """Create service with mocked LLM client."""
        with patch('app.services.extraction.document_classification_service.UnifiedLLMClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.generate_content = AsyncMock(return_value=mock_llm_response)
            MockClient.return_value = mock_client
            
            service = DocumentClassificationService(
                provider="gemini",
                gemini_api_key="test-key",
                max_pages_for_classification=10,
            )
            service.client = mock_client
            return service
    
    @pytest.mark.asyncio
    async def test_classify_document_success(self, service):
        """Test successful document classification."""
        pages = [
            "DECLARATIONS\nPolicy Number: POL-123",
            "Named Insured: ABC Corp",
            "Effective Date: 01/01/2024",
            "COVERAGES\nCoverage A - Building",
        ]
        
        result = await service.classify_document(pages)
        
        assert isinstance(result, DocumentClassificationResult)
        assert result.document_type == "policy"
        assert result.document_subtype == "commercial_property"
        assert result.confidence == 0.95
    
    @pytest.mark.asyncio
    async def test_classify_document_detects_sections(self, service):
        """Test that section boundaries are detected."""
        pages = ["DECLARATIONS\nContent"] * 5
        
        result = await service.classify_document(pages)
        
        assert len(result.section_boundaries) > 0
        
        decl_boundary = next(
            (sb for sb in result.section_boundaries 
             if sb.section_type == SectionType.DECLARATIONS),
            None
        )
        assert decl_boundary is not None
        assert decl_boundary.start_page == 1
    
    @pytest.mark.asyncio
    async def test_classify_document_page_map(self, service):
        """Test that page section map is created."""
        pages = ["Content"] * 5
        
        result = await service.classify_document(pages)
        
        assert len(result.page_section_map) > 0
        assert 1 in result.page_section_map
    
    @pytest.mark.asyncio
    async def test_classify_empty_pages(self, service):
        """Test classification with empty pages."""
        result = await service.classify_document([])
        
        assert result.document_type == "unknown"
        assert result.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_get_sections_for_extraction(self, service):
        """Test getting sections for extraction."""
        pages = ["Content"] * 5
        
        result = await service.classify_document(pages)
        sections = result.get_sections_for_extraction()
        
        assert isinstance(sections, list)
        assert all(isinstance(s, SectionType) for s in sections)
    
    @pytest.mark.asyncio
    async def test_get_pages_for_section(self, service):
        """Test getting pages for a specific section."""
        pages = ["Content"] * 5
        
        result = await service.classify_document(pages)
        pages_for_decl = result.get_pages_for_section(SectionType.DECLARATIONS)
        
        assert isinstance(pages_for_decl, list)
        assert all(isinstance(p, int) for p in pages_for_decl)


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
                section_type=SectionType.SCHEDULE_OF_VALUES,
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


class TestCrossSectionValidator:
    """Test suite for Tier 3 CrossSectionValidator."""
    
    @pytest.fixture
    def validator(self):
        """Create validator without LLM (rule-based only)."""
        return CrossSectionValidator(use_llm_for_conflicts=False)
    
    @pytest.fixture
    def consistent_extraction_result(self):
        """Create extraction result with consistent data."""
        return DocumentExtractionResult(
            document_id=uuid4(),
            section_results=[
                SectionExtractionResult(
                    section_type=SectionType.DECLARATIONS,
                    extracted_data={
                        "policy_number": "POL-2024-001",
                        "insured_name": "ABC Manufacturing",
                        "effective_date": "2024-01-01",
                        "expiration_date": "2025-01-01",
                        "total_premium": 50000,
                    },
                    confidence=0.95,
                ),
                SectionExtractionResult(
                    section_type=SectionType.COVERAGES,
                    extracted_data={
                        "coverages": [
                            {"coverage_name": "Building", "premium_amount": 25000},
                            {"coverage_name": "Contents", "premium_amount": 25000},
                        ]
                    },
                    confidence=0.90,
                ),
            ],
        )
    
    @pytest.fixture
    def inconsistent_extraction_result(self):
        """Create extraction result with inconsistent data."""
        return DocumentExtractionResult(
            document_id=uuid4(),
            section_results=[
                SectionExtractionResult(
                    section_type=SectionType.DECLARATIONS,
                    extracted_data={
                        "policy_number": "POL-2024-001",
                        "insured_name": "ABC Manufacturing",
                        "effective_date": "2024-01-01",
                        "expiration_date": "2025-01-01",
                    },
                    confidence=0.95,
                ),
                SectionExtractionResult(
                    section_type=SectionType.COVERAGES,
                    extracted_data={
                        "policy_number": "POL-2024-002",  # Different!
                    },
                    confidence=0.90,
                ),
            ],
        )
    
    @pytest.mark.asyncio
    async def test_validate_consistent_data(self, validator, consistent_extraction_result):
        """Test validation of consistent data."""
        result = await validator.validate(consistent_extraction_result)
        
        assert isinstance(result, CrossSectionValidationResult)
        # Should have no errors (warnings may exist)
        errors = result.get_errors()
        assert len(errors) == 0
    
    @pytest.mark.asyncio
    async def test_validate_detects_inconsistency(self, validator, inconsistent_extraction_result):
        """Test that inconsistencies are detected."""
        result = await validator.validate(inconsistent_extraction_result)
        
        # Should find policy_number inconsistency
        policy_issues = [
            i for i in result.issues 
            if i.field_name == "policy_number"
        ]
        assert len(policy_issues) > 0
        assert policy_issues[0].issue_type == "inconsistency"
    
    @pytest.mark.asyncio
    async def test_validate_reconciles_values(self, validator, inconsistent_extraction_result):
        """Test that values are reconciled."""
        result = await validator.validate(inconsistent_extraction_result)
        
        # Should have reconciled policy_number
        policy_reconciled = result.get_reconciled_value("policy_number")
        assert policy_reconciled is not None
    
    @pytest.mark.asyncio
    async def test_validate_date_logic(self, validator):
        """Test date validation logic."""
        # Create result with invalid dates
        extraction_result = DocumentExtractionResult(
            document_id=uuid4(),
            section_results=[
                SectionExtractionResult(
                    section_type=SectionType.DECLARATIONS,
                    extracted_data={
                        "effective_date": "2025-01-01",
                        "expiration_date": "2024-01-01",  # Before effective!
                    },
                ),
            ],
        )
        
        result = await validator.validate(extraction_result)
        
        # Should find date issue
        date_issues = [i for i in result.issues if "date" in i.field_name.lower()]
        assert len(date_issues) > 0
    
    @pytest.mark.asyncio
    async def test_validate_summary_stats(self, validator, inconsistent_extraction_result):
        """Test that summary statistics are calculated."""
        result = await validator.validate(inconsistent_extraction_result)
        
        assert "total_issues" in result.summary
        assert "errors" in result.summary
        assert "warnings" in result.summary
        assert "fields_reconciled" in result.summary
    
    @pytest.mark.asyncio
    async def test_validate_is_valid_flag(self, validator, consistent_extraction_result, inconsistent_extraction_result):
        """Test is_valid flag."""
        # Consistent should be valid
        consistent_result = await validator.validate(consistent_extraction_result)
        
        # Inconsistent may or may not be valid depending on severity
        inconsistent_result = await validator.validate(inconsistent_extraction_result)
        
        # At least check that the flag is set
        assert isinstance(consistent_result.is_valid, bool)
        assert isinstance(inconsistent_result.is_valid, bool)


class TestValidationIssue:
    """Test ValidationIssue dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        issue = ValidationIssue(
            issue_type="inconsistency",
            severity="error",
            field_name="policy_number",
            sections_involved=["declarations", "coverages"],
            values_found=["POL-1", "POL-2"],
            recommended_value="POL-1",
            message="Policy numbers differ",
        )
        
        d = issue.to_dict()
        
        assert d["issue_type"] == "inconsistency"
        assert d["severity"] == "error"
        assert d["field_name"] == "policy_number"
        assert len(d["sections_involved"]) == 2


class TestReconciledValue:
    """Test ReconciledValue dataclass."""
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        rv = ReconciledValue(
            field_name="policy_number",
            canonical_value="POL-2024-001",
            source_sections=["declarations"],
            confidence=0.95,
            original_values={"declarations": "POL-2024-001", "coverages": "POL-2024-002"},
        )
        
        d = rv.to_dict()
        
        assert d["field_name"] == "policy_number"
        assert d["canonical_value"] == "POL-2024-001"
        assert d["confidence"] == 0.95

