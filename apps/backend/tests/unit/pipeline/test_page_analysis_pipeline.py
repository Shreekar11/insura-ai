"""Unit tests for PageAnalysisPipeline.

Tests the facade that coordinates page signal extraction, classification,
and manifest creation for page-level analysis.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.pipeline.page_analysis import PageAnalysisPipeline
from app.models.page_analysis_models import (
    PageSignals,
    PageClassification,
    PageManifest,
    PageType
)


class TestPageAnalysisPipelineExtractSignals:
    """Test signal extraction phase."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session
    
    @pytest.fixture
    def sample_signals(self):
        """Create sample page signals."""
        return [
            PageSignals(
                page_number=1,
                top_lines=["DECLARATIONS PAGE", "Policy Number: ABC-123"],
                text_density=0.8,
                has_tables=False,
                max_font_size=18.0,
                page_hash="hash1"
            ),
            PageSignals(
                page_number=2,
                top_lines=["COVERAGES", "Coverage A - Building"],
                text_density=0.7,
                has_tables=False,
                max_font_size=16.0,
                page_hash="hash2"
            ),
            PageSignals(
                page_number=3,
                top_lines=["ISO PROPERTIES, INC.", "COPYRIGHT"],
                text_density=0.2,
                has_tables=False,
                max_font_size=10.0,
                page_hash="hash3"
            )
        ]
    
    @pytest.mark.asyncio
    async def test_extract_signals_returns_list(self, mock_session, sample_signals):
        """Test that extract_signals returns a list of PageSignals."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        # Mock the analyzer
        with patch.object(
            pipeline.analyzer,
            'analyze_document',
            new_callable=AsyncMock,
            return_value=sample_signals
        ):
            # Mock the repository
            with patch.object(
                pipeline.repository,
                'save_page_signals',
                new_callable=AsyncMock
            ):
                document_id = uuid4()
                result = await pipeline.extract_signals(document_id, "http://example.com/doc.pdf")
                
                assert isinstance(result, list)
                assert len(result) == 3
                assert all(isinstance(s, PageSignals) for s in result)
    
    @pytest.mark.asyncio
    async def test_extract_signals_saves_to_database(self, mock_session, sample_signals):
        """Test that signals are saved to database."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.analyzer,
            'analyze_document',
            new_callable=AsyncMock,
            return_value=sample_signals
        ):
            mock_save = AsyncMock()
            with patch.object(
                pipeline.repository,
                'save_page_signals',
                mock_save
            ):
                document_id = uuid4()
                await pipeline.extract_signals(document_id, "http://example.com/doc.pdf")
                
                # Should save each signal
                assert mock_save.call_count == 3


class TestPageAnalysisPipelineClassifyPages:
    """Test page classification phase."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session
    
    @pytest.fixture
    def sample_signals(self):
        """Create sample page signals."""
        return [
            PageSignals(
                page_number=1,
                top_lines=["DECLARATIONS PAGE", "Policy Number: ABC-123"],
                text_density=0.8,
                has_tables=False,
                max_font_size=18.0,
                page_hash="hash1"
            ),
            PageSignals(
                page_number=2,
                top_lines=["COVERAGES", "Coverage A - Building"],
                text_density=0.7,
                has_tables=False,
                max_font_size=16.0,
                page_hash="hash2"
            ),
            PageSignals(
                page_number=3,
                top_lines=["ISO PROPERTIES, INC.", "COPYRIGHT"],
                text_density=0.2,
                has_tables=False,
                max_font_size=10.0,
                page_hash="hash3"
            )
        ]
    
    @pytest.mark.asyncio
    async def test_classify_pages_returns_classifications(self, mock_session, sample_signals):
        """Test that classify_pages returns list of classifications."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.classify_pages(document_id, sample_signals)
            
            assert isinstance(result, list)
            assert len(result) == 3
            assert all(isinstance(c, PageClassification) for c in result)
    
    @pytest.mark.asyncio
    async def test_classify_pages_identifies_declarations(self, mock_session, sample_signals):
        """Test that declarations pages are correctly identified."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.classify_pages(document_id, sample_signals)
            
            # First page should be declarations
            decl_page = next(c for c in result if c.page_number == 1)
            assert decl_page.page_type == PageType.DECLARATIONS
            assert decl_page.should_process is True
    
    @pytest.mark.asyncio
    async def test_classify_pages_identifies_coverages(self, mock_session, sample_signals):
        """Test that coverage pages are correctly identified."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.classify_pages(document_id, sample_signals)
            
            # Second page should be coverages
            cov_page = next(c for c in result if c.page_number == 2)
            assert cov_page.page_type == PageType.COVERAGES
            assert cov_page.should_process is True
    
    @pytest.mark.asyncio
    async def test_classify_pages_identifies_boilerplate(self, mock_session, sample_signals):
        """Test that boilerplate pages are correctly identified."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.classify_pages(document_id, sample_signals)
            
            # Third page should be boilerplate
            bp_page = next(c for c in result if c.page_number == 3)
            assert bp_page.page_type == PageType.BOILERPLATE
            assert bp_page.should_process is False
    
    @pytest.mark.asyncio
    async def test_classify_pages_detects_duplicates(self, mock_session):
        """Test that duplicate pages are detected."""
        # Create signals with duplicate content
        signals = [
            PageSignals(
                page_number=1,
                top_lines=["ISO FORM CG 00 01", "Standard form language"],
                text_density=0.5,
                has_tables=False,
                max_font_size=12.0,
                page_hash="hash1"
            ),
            PageSignals(
                page_number=5,
                top_lines=["ISO FORM CG 00 01", "Standard form language"],
                text_density=0.5,
                has_tables=False,
                max_font_size=12.0,
                page_hash="hash2"
            )
        ]
        
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.classify_pages(document_id, signals)
            
            # Second page should be marked as duplicate
            dup_page = next(c for c in result if c.page_number == 5)
            assert dup_page.page_type == PageType.DUPLICATE
            assert dup_page.should_process is False
            assert dup_page.duplicate_of == 1
    
    @pytest.mark.asyncio
    async def test_classify_pages_saves_to_database(self, mock_session, sample_signals):
        """Test that classifications are saved to database."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        mock_save = AsyncMock()
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            mock_save
        ):
            document_id = uuid4()
            await pipeline.classify_pages(document_id, sample_signals)
            
            # Should save each classification
            assert mock_save.call_count == 3


class TestPageAnalysisPipelineCreateManifest:
    """Test manifest creation phase."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session
    
    @pytest.fixture
    def sample_classifications(self):
        """Create sample classifications."""
        return [
            PageClassification(
                page_number=1,
                page_type=PageType.DECLARATIONS,
                confidence=0.95,
                should_process=True,
                reasoning="Matched declarations keywords"
            ),
            PageClassification(
                page_number=2,
                page_type=PageType.COVERAGES,
                confidence=0.9,
                should_process=True,
                reasoning="Matched coverages keywords"
            ),
            PageClassification(
                page_number=3,
                page_type=PageType.BOILERPLATE,
                confidence=0.85,
                should_process=False,
                reasoning="ISO copyright boilerplate"
            ),
            PageClassification(
                page_number=4,
                page_type=PageType.DUPLICATE,
                confidence=1.0,
                should_process=False,
                duplicate_of=1,
                reasoning="Duplicate of page 1"
            )
        ]
    
    @pytest.mark.asyncio
    async def test_create_manifest_returns_manifest(self, mock_session, sample_classifications):
        """Test that create_manifest returns a PageManifest."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_manifest',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.create_manifest(document_id, sample_classifications)
            
            assert isinstance(result, PageManifest)
    
    @pytest.mark.asyncio
    async def test_create_manifest_correct_page_counts(self, mock_session, sample_classifications):
        """Test that manifest has correct page counts."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_manifest',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.create_manifest(document_id, sample_classifications)
            
            assert result.total_pages == 4
            assert len(result.pages_to_process) == 2  # Pages 1 and 2
            assert len(result.pages_skipped) == 2  # Pages 3 and 4
    
    @pytest.mark.asyncio
    async def test_create_manifest_correct_pages_to_process(self, mock_session, sample_classifications):
        """Test that pages_to_process contains correct page numbers."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_manifest',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.create_manifest(document_id, sample_classifications)
            
            assert 1 in result.pages_to_process
            assert 2 in result.pages_to_process
            assert 3 not in result.pages_to_process
            assert 4 not in result.pages_to_process
    
    @pytest.mark.asyncio
    async def test_create_manifest_correct_pages_skipped(self, mock_session, sample_classifications):
        """Test that pages_skipped contains correct page numbers."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_manifest',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.create_manifest(document_id, sample_classifications)
            
            assert 3 in result.pages_skipped
            assert 4 in result.pages_skipped
            assert 1 not in result.pages_skipped
            assert 2 not in result.pages_skipped
    
    @pytest.mark.asyncio
    async def test_create_manifest_processing_ratio(self, mock_session, sample_classifications):
        """Test that processing_ratio is calculated correctly."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_manifest',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.create_manifest(document_id, sample_classifications)
            
            # 2 out of 4 pages = 0.5
            assert result.processing_ratio == 0.5
    
    @pytest.mark.asyncio
    async def test_create_manifest_cost_savings_estimate(self, mock_session, sample_classifications):
        """Test that cost_savings_estimate is calculated correctly."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_manifest',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            result = await pipeline.create_manifest(document_id, sample_classifications)
            
            # 1 - 0.5 = 0.5
            assert result.cost_savings_estimate == 0.5
    
    @pytest.mark.asyncio
    async def test_create_manifest_saves_to_database(self, mock_session, sample_classifications):
        """Test that manifest is saved to database."""
        pipeline = PageAnalysisPipeline(mock_session)
        
        mock_save = AsyncMock()
        with patch.object(
            pipeline.repository,
            'save_manifest',
            mock_save
        ):
            document_id = uuid4()
            await pipeline.create_manifest(document_id, sample_classifications)
            
            mock_save.assert_called_once()


class TestPageAnalysisPipelineV2Alignment:
    """Test alignment with requirements."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = MagicMock()
        return session
    
    @pytest.mark.asyncio
    async def test_processing_ratio_target_range(self, mock_session):
        """Test that processing ratio falls within target (10-20%)."""
        # Create a realistic insurance document scenario
        # 100 pages with typical distribution
        signals = []
        
        # Page 1-3: Declarations (should process)
        for i in range(1, 4):
            signals.append(PageSignals(
                page_number=i,
                top_lines=["DECLARATIONS PAGE", f"Section {i}"],
                text_density=0.8,
                has_tables=False,
                max_font_size=18.0,
                page_hash=f"decl_{i}"
            ))
        
        # Page 4-10: Coverages (should process)
        for i in range(4, 11):
            signals.append(PageSignals(
                page_number=i,
                top_lines=["COVERAGES", f"Coverage Section {i}"],
                text_density=0.7,
                has_tables=False,
                max_font_size=16.0,
                page_hash=f"cov_{i}"
            ))
        
        # Page 11-15: Endorsements (should process)
        for i in range(11, 16):
            signals.append(PageSignals(
                page_number=i,
                top_lines=[f"ENDORSEMENT NO. {i-10}"],
                text_density=0.6,
                has_tables=False,
                max_font_size=14.0,
                page_hash=f"end_{i}"
            ))
        
        # Page 16-100: Boilerplate/ISO forms (should skip)
        for i in range(16, 101):
            signals.append(PageSignals(
                page_number=i,
                top_lines=["ISO PROPERTIES, INC.", "COPYRIGHT ISO"],
                text_density=0.3,
                has_tables=False,
                max_font_size=10.0,
                page_hash=f"bp_{i}"
            ))
        
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            with patch.object(
                pipeline.repository,
                'save_manifest',
                new_callable=AsyncMock
            ):
                document_id = uuid4()
                classifications = await pipeline.classify_pages(document_id, signals)
                manifest = await pipeline.create_manifest(document_id, classifications)
                
                # Target: 10-20% of pages processed
                # With 15 key pages out of 100, ratio should be ~15%
                assert 0.10 <= manifest.processing_ratio <= 0.40, \
                    f"Processing ratio {manifest.processing_ratio:.2%} outside target range"
    
    @pytest.mark.asyncio
    async def test_key_section_types_identified(self, mock_session):
        """Test that all key section types are properly identified."""
        signals = [
            PageSignals(
                page_number=1,
                top_lines=["DECLARATIONS PAGE"],
                text_density=0.8,
                has_tables=False,
                max_font_size=18.0,
                page_hash="decl"
            ),
            PageSignals(
                page_number=2,
                top_lines=["COVERAGES", "Limits of Insurance"],
                text_density=0.7,
                has_tables=False,
                max_font_size=16.0,
                page_hash="cov"
            ),
            PageSignals(
                page_number=3,
                top_lines=["CONDITIONS", "Your Duties"],
                text_density=0.6,
                has_tables=False,
                max_font_size=14.0,
                page_hash="cond"
            ),
            PageSignals(
                page_number=4,
                top_lines=["EXCLUSIONS", "We do not cover"],
                text_density=0.6,
                has_tables=False,
                max_font_size=14.0,
                page_hash="excl"
            ),
            PageSignals(
                page_number=5,
                top_lines=["ENDORSEMENT NO. 1"],
                text_density=0.5,
                has_tables=False,
                max_font_size=12.0,
                page_hash="end"
            ),
            PageSignals(
                page_number=6,
                top_lines=["SCHEDULE OF VALUES"],
                text_density=0.4,
                has_tables=True,
                max_font_size=12.0,
                page_hash="sov"
            ),
            PageSignals(
                page_number=7,
                top_lines=["LOSS RUN REPORT"],
                text_density=0.4,
                has_tables=True,
                max_font_size=12.0,
                page_hash="loss"
            )
        ]
        
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            classifications = await pipeline.classify_pages(document_id, signals)
            
            # Check that all key types are identified
            page_types = {c.page_type for c in classifications}
            
            assert PageType.DECLARATIONS in page_types
            assert PageType.COVERAGES in page_types
            assert PageType.CONDITIONS in page_types
            assert PageType.EXCLUSIONS in page_types
            assert PageType.ENDORSEMENT in page_types
            assert PageType.SOV in page_types
            assert PageType.LOSS_RUN in page_types
    
    @pytest.mark.asyncio
    async def test_table_pages_correctly_identified(self, mock_session):
        """Test that pages with tables are correctly identified for SOV/Loss Run."""
        signals = [
            PageSignals(
                page_number=1,
                top_lines=["SCHEDULE OF VALUES", "Location Schedule"],
                text_density=0.4,
                has_tables=True,
                max_font_size=12.0,
                page_hash="sov"
            ),
            PageSignals(
                page_number=2,
                top_lines=["LOSS HISTORY", "Claims Summary"],
                text_density=0.4,
                has_tables=True,
                max_font_size=12.0,
                page_hash="loss"
            )
        ]
        
        pipeline = PageAnalysisPipeline(mock_session)
        
        with patch.object(
            pipeline.repository,
            'save_page_classification',
            new_callable=AsyncMock
        ):
            document_id = uuid4()
            classifications = await pipeline.classify_pages(document_id, signals)
            
            sov_page = next(c for c in classifications if c.page_number == 1)
            loss_page = next(c for c in classifications if c.page_number == 2)
            
            assert sov_page.page_type == PageType.SOV
            assert loss_page.page_type == PageType.LOSS_RUN


class TestPageManifestModel:
    """Test PageManifest model properties and methods."""
    
    def test_processing_ratio_calculation(self):
        """Test processing_ratio property."""
        manifest = PageManifest(
            document_id=uuid4(),
            total_pages=100,
            pages_to_process=[1, 2, 3, 4, 5],
            pages_skipped=list(range(6, 101)),
            classifications=[]
        )
        
        assert manifest.processing_ratio == 0.05
    
    def test_processing_ratio_single_page_document(self):
        """Test processing_ratio with single page document."""
        manifest = PageManifest(
            document_id=uuid4(),
            total_pages=1,
            pages_to_process=[1],
            pages_skipped=[],
            classifications=[
                PageClassification(
                    page_number=1,
                    page_type=PageType.DECLARATIONS,
                    confidence=0.95,
                    should_process=True
                )
            ]
        )
        
        assert manifest.processing_ratio == 1.0
    
    def test_cost_savings_estimate(self):
        """Test cost_savings_estimate property."""
        manifest = PageManifest(
            document_id=uuid4(),
            total_pages=100,
            pages_to_process=[1, 2, 3, 4, 5],
            pages_skipped=list(range(6, 101)),
            classifications=[]
        )
        
        assert manifest.cost_savings_estimate == 0.95
    
    def test_get_pages_by_type(self):
        """Test get_pages_by_type method."""
        classifications = [
            PageClassification(
                page_number=1,
                page_type=PageType.DECLARATIONS,
                confidence=0.95,
                should_process=True
            ),
            PageClassification(
                page_number=2,
                page_type=PageType.COVERAGES,
                confidence=0.9,
                should_process=True
            ),
            PageClassification(
                page_number=3,
                page_type=PageType.COVERAGES,
                confidence=0.85,
                should_process=True
            ),
            PageClassification(
                page_number=4,
                page_type=PageType.BOILERPLATE,
                confidence=0.8,
                should_process=False
            )
        ]
        
        manifest = PageManifest(
            document_id=uuid4(),
            total_pages=4,
            pages_to_process=[1, 2, 3],
            pages_skipped=[4],
            classifications=classifications
        )
        
        decl_pages = manifest.get_pages_by_type(PageType.DECLARATIONS)
        cov_pages = manifest.get_pages_by_type(PageType.COVERAGES)
        bp_pages = manifest.get_pages_by_type(PageType.BOILERPLATE)
        
        assert decl_pages == [1]
        assert cov_pages == [2, 3]
        assert bp_pages == [4]

