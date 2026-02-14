"""Unit tests for VectorRetrievalService.

Tests:
- Full retrieval pipeline (embed -> search -> rerank -> resolve)
- Query embedding generation
- Content resolution from SectionExtraction
- Document name resolution
- Page info extraction
- Edge cases (no results, missing data)
"""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.schemas.query import (
    ExtractedQueryEntities,
    QueryPlan,
    VectorSearchResult,
    WorkflowContext,
)
from app.services.retrieval.vector.vector_retrieval_service import (
    VectorRetrievalService,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

DOC_ID_1 = uuid4()
DOC_ID_2 = uuid4()
WORKFLOW_ID = uuid4()
EMB_ID_1 = uuid4()
EMB_ID_2 = uuid4()
CANONICAL_ID = uuid4()


def _make_embedding_mock(
    emb_id=None,
    document_id=None,
    section_type="coverages",
    entity_type="coverage",
    entity_id="coverages_cov_0",
    canonical_entity_id=None,
    effective_date=None,
):
    emb = MagicMock()
    emb.id = emb_id or uuid4()
    emb.document_id = document_id or DOC_ID_1
    emb.section_type = section_type
    emb.entity_type = entity_type
    emb.entity_id = entity_id
    emb.canonical_entity_id = canonical_entity_id
    emb.effective_date = effective_date
    return emb


_SENTINEL = object()


def _make_section_extraction(
    document_id=None,
    section_type="coverages",
    extracted_fields=None,
    page_range=_SENTINEL,
):
    extraction = MagicMock()
    extraction.document_id = document_id or DOC_ID_1
    extraction.section_type = section_type
    extraction.extracted_fields = extracted_fields or {
        "coverages": [
            {"name": "General Liability", "limit": "$1,000,000", "deductible": "$5,000"},
            {"name": "Property", "limit": "$2,000,000", "deductible": "$10,000"},
        ]
    }
    extraction.page_range = {"start": 3, "end": 5} if page_range is _SENTINEL else page_range
    return extraction


def _make_query_plan(
    query="What is my property deductible?",
    intent="QA",
    traversal_depth=1,
    expanded_queries=None,
    target_document_ids=None,
    section_type_filters=_SENTINEL,
    entity_type_filters=_SENTINEL,
):
    return QueryPlan(
        original_query=query,
        intent=intent,
        traversal_depth=traversal_depth,
        extracted_entities=ExtractedQueryEntities(
            coverage_types=["property"],
            section_hints=["coverages"],
        ),
        expanded_queries=expanded_queries
        or [
            "What is my property deductible?",
            "What is my property self-insured retention?",
        ],
        workflow_context=WorkflowContext(
            workflow_id=WORKFLOW_ID,
            sections=[],
            entities=[],
            document_ids=[DOC_ID_1, DOC_ID_2],
            document_count=2,
        ),
        target_document_ids=target_document_ids,
        section_type_filters=["coverages", "declarations"] if section_type_filters is _SENTINEL else section_type_filters,
        entity_type_filters=["coverage"] if entity_type_filters is _SENTINEL else entity_type_filters,
    )


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    """Create VectorRetrievalService with mocked dependencies."""
    svc = VectorRetrievalService.__new__(VectorRetrievalService)
    svc.db_session = mock_session
    svc.vector_repo = AsyncMock()
    svc.section_repo = AsyncMock()
    svc.template_service = MagicMock()
    svc.reranker = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# Tests: _embed_queries
# ---------------------------------------------------------------------------


class TestEmbedQueries:
    """Tests for query embedding generation."""

    @pytest.mark.asyncio
    async def test_embed_queries_returns_embeddings(self, service):
        """Should return list of float lists for each query."""
        import numpy as np

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array(
            [[0.1] * 384, [0.2] * 384]
        )

        with patch(
            "app.services.retrieval.vector.vector_retrieval_service._get_embedding_model",
            return_value=mock_model,
        ):
            result = await service._embed_queries(
                ["query 1", "query 2"]
            )

        assert len(result) == 2
        assert len(result[0]) == 384
        mock_model.encode.assert_called_once_with(["query 1", "query 2"])

    @pytest.mark.asyncio
    async def test_embed_queries_empty_returns_empty(self, service):
        """Empty query list should return empty embeddings."""
        result = await service._embed_queries([])
        assert result == []


# ---------------------------------------------------------------------------
# Tests: _resolve_document_names
# ---------------------------------------------------------------------------


class TestResolveDocumentNames:
    """Tests for document name resolution."""

    @pytest.mark.asyncio
    async def test_resolve_document_names(self, service, mock_session):
        """Should map document IDs to filenames from file_path."""
        row1 = MagicMock()
        row1.id = DOC_ID_1
        row1.file_path = "/uploads/POL_CA_00_01.pdf"
        row2 = MagicMock()
        row2.id = DOC_ID_2
        row2.file_path = "/uploads/subdir/endorsement.pdf"

        mock_result = MagicMock()
        mock_result.__iter__ = MagicMock(return_value=iter([row1, row2]))
        mock_session.execute.return_value = mock_result

        names = await service._resolve_document_names([DOC_ID_1, DOC_ID_2])

        assert names[DOC_ID_1] == "POL_CA_00_01.pdf"
        assert names[DOC_ID_2] == "endorsement.pdf"

    @pytest.mark.asyncio
    async def test_resolve_document_names_empty(self, service):
        """Empty document IDs should return empty dict."""
        names = await service._resolve_document_names([])
        assert names == {}


# ---------------------------------------------------------------------------
# Tests: _resolve_content_map
# ---------------------------------------------------------------------------


class TestResolveContentMap:
    """Tests for content map resolution from SectionExtraction."""

    @pytest.mark.asyncio
    async def test_resolve_content_map(self, service):
        """Should fetch section extractions for each (doc_id, section_type) key."""
        extraction = _make_section_extraction()
        service.section_repo.get_by_document.return_value = [extraction]

        section_keys = [(DOC_ID_1, "coverages")]
        content_map = await service._resolve_content_map(section_keys, WORKFLOW_ID)

        assert (DOC_ID_1, "coverages") in content_map
        assert len(content_map[(DOC_ID_1, "coverages")]) == 1
        service.section_repo.get_by_document.assert_called_once_with(
            document_id=DOC_ID_1,
            section_type="coverages",
            workflow_id=WORKFLOW_ID,
        )

    @pytest.mark.asyncio
    async def test_resolve_content_map_multiple_keys(self, service):
        """Should handle multiple section keys."""
        service.section_repo.get_by_document.return_value = []

        section_keys = [(DOC_ID_1, "coverages"), (DOC_ID_2, "exclusions")]
        content_map = await service._resolve_content_map(section_keys, WORKFLOW_ID)

        assert len(content_map) == 2
        assert service.section_repo.get_by_document.call_count == 2


# ---------------------------------------------------------------------------
# Tests: _resolve_entity_content
# ---------------------------------------------------------------------------


class TestResolveEntityContent:
    """Tests for entity content resolution."""

    def setup_method(self):
        self.service = VectorRetrievalService.__new__(VectorRetrievalService)
        self.service.template_service = AsyncMock()
        # Template service returns None to force _format_entity_data fallback path
        self.service.template_service.run.return_value = None

    @pytest.mark.asyncio
    async def test_resolve_content_with_list_entities(self):
        """Should resolve content from extracted_fields list by index."""
        emb = _make_embedding_mock(entity_id="coverages_cov_1")
        extraction = _make_section_extraction(
            extracted_fields={
                "coverages": [
                    {"name": "GL", "limit": "$1M"},
                    {"name": "Property", "limit": "$2M"},
                ]
            }
        )
        content_map = {(DOC_ID_1, "coverages"): [extraction]}

        content = await self.service._resolve_entity_content(emb, content_map)

        assert "Property" in content
        assert "$2M" in content

    @pytest.mark.asyncio
    async def test_resolve_content_first_item_fallback(self):
        """Should return first item if index cannot be parsed."""
        emb = _make_embedding_mock(entity_id="coverages_general")
        extraction = _make_section_extraction(
            extracted_fields={
                "coverages": [{"name": "GL", "limit": "$1M"}]
            }
        )
        content_map = {(DOC_ID_1, "coverages"): [extraction]}

        content = await self.service._resolve_entity_content(emb, content_map)
        assert "GL" in content

    @pytest.mark.asyncio
    async def test_resolve_content_flat_dict(self):
        """Should handle flat dict extracted_fields (no list)."""
        emb = _make_embedding_mock(
            entity_id="declarations_dec_0", section_type="declarations"
        )
        extraction = _make_section_extraction(
            section_type="declarations",
            extracted_fields={
                "policy_number": "POL-123",
                "insured": "Acme Corp",
                "effective_date": "2024-01-01",
            },
        )
        content_map = {(DOC_ID_1, "declarations"): [extraction]}

        content = await self.service._resolve_entity_content(emb, content_map)
        assert "POL-123" in content

    @pytest.mark.asyncio
    async def test_resolve_content_no_extraction(self):
        """Should return fallback string when no extraction found."""
        emb = _make_embedding_mock(section_type="endorsements")
        content_map = {}

        content = await self.service._resolve_entity_content(emb, content_map)
        assert "endorsements" in content
        assert "unavailable" in content

    @pytest.mark.asyncio
    async def test_resolve_content_empty_fields(self):
        """Should return section summary when extracted_fields is empty."""
        emb = _make_embedding_mock(entity_id="coverages_cov_0")
        extraction = _make_section_extraction(extracted_fields={})
        content_map = {(DOC_ID_1, "coverages"): [extraction]}

        content = await self.service._resolve_entity_content(emb, content_map)
        assert "coverages" in content


# ---------------------------------------------------------------------------
# Tests: _find_entity_in_fields
# ---------------------------------------------------------------------------


class TestFindEntityInFields:
    """Tests for entity lookup within extracted_fields."""

    def setup_method(self):
        self.service = VectorRetrievalService.__new__(VectorRetrievalService)

    def test_find_by_index(self):
        """Should find entity by parsed index from suffix."""
        fields = {"items": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}
        result = self.service._find_entity_in_fields(fields, "item_1", "coverage")
        assert result == {"name": "B"}

    def test_find_index_zero(self):
        """Should find first item with index 0."""
        fields = {"coverages": [{"name": "GL"}, {"name": "PL"}]}
        result = self.service._find_entity_in_fields(fields, "cov_0", "coverage")
        assert result == {"name": "GL"}

    def test_find_index_out_of_range(self):
        """Index beyond list length should return None (no suitable list)."""
        fields = {"coverages": [{"name": "GL"}]}
        result = self.service._find_entity_in_fields(fields, "cov_5", "coverage")
        assert result is None

    def test_find_flat_dict_fallback(self):
        """Should return flat dict itself when no lists present."""
        fields = {"policy_number": "POL-123", "insured": "Acme"}
        result = self.service._find_entity_in_fields(fields, "dec_0", "policy")
        assert result == fields

    def test_find_no_match(self):
        """Should return None when fields has no matching entity data."""
        fields = {"metadata": "some string"}
        result = self.service._find_entity_in_fields(fields, "cov_1", "coverage")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: _extract_page_info
# ---------------------------------------------------------------------------


class TestExtractPageInfo:
    """Tests for page information extraction."""

    def setup_method(self):
        self.service = VectorRetrievalService.__new__(VectorRetrievalService)

    def test_extract_page_info_from_page_range(self):
        """Should extract page_numbers and page_range from SectionExtraction."""
        emb = _make_embedding_mock()
        extraction = _make_section_extraction(page_range={"start": 3, "end": 5})
        content_map = {(DOC_ID_1, "coverages"): [extraction]}

        page_numbers, page_range = self.service._extract_page_info(emb, content_map)

        assert page_numbers == [3, 4, 5]
        assert page_range == {"start": 3, "end": 5}

    def test_extract_page_info_single_page(self):
        """Should handle single-page range."""
        emb = _make_embedding_mock()
        extraction = _make_section_extraction(page_range={"start": 7, "end": 7})
        content_map = {(DOC_ID_1, "coverages"): [extraction]}

        page_numbers, page_range = self.service._extract_page_info(emb, content_map)

        assert page_numbers == [7]
        assert page_range == {"start": 7, "end": 7}

    def test_extract_page_info_no_extraction(self):
        """Should return empty when no extraction found."""
        emb = _make_embedding_mock()
        content_map = {}

        page_numbers, page_range = self.service._extract_page_info(emb, content_map)

        assert page_numbers == []
        assert page_range is None

    def test_extract_page_info_no_page_range(self):
        """Should return empty when page_range is None."""
        emb = _make_embedding_mock()
        extraction = _make_section_extraction(page_range=None)
        content_map = {(DOC_ID_1, "coverages"): [extraction]}

        page_numbers, page_range = self.service._extract_page_info(emb, content_map)

        assert page_numbers == []
        assert page_range is None


# ---------------------------------------------------------------------------
# Tests: Full retrieve() pipeline
# ---------------------------------------------------------------------------


class TestRetrievePipeline:
    """Integration-level tests for the full retrieve() method."""

    @pytest.fixture(autouse=True)
    def setup_service(self, service):
        self.service = service
        self.query_plan = _make_query_plan()

    @pytest.mark.asyncio
    async def test_retrieve_empty_when_no_embeddings(self):
        """Should return empty list when embed returns nothing."""
        with patch.object(
            self.service, "_embed_queries", return_value=[]
        ):
            results = await self.service.retrieve(self.query_plan)
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_empty_when_no_search_results(self):
        """Should return empty list when vector search finds nothing."""
        with patch.object(
            self.service,
            "_embed_queries",
            return_value=[[0.1] * 384],
        ):
            self.service.vector_repo.semantic_search_multi_query.return_value = []
            results = await self.service.retrieve(self.query_plan)
        assert results == []

    @pytest.mark.asyncio
    async def test_retrieve_full_pipeline(self):
        """Should execute full pipeline: embed -> search -> rerank -> resolve."""
        emb1 = _make_embedding_mock(
            emb_id=EMB_ID_1,
            document_id=DOC_ID_1,
            entity_id="coverages_cov_0",
            section_type="coverages",
            entity_type="coverage",
            effective_date=date(2024, 1, 1),
        )
        emb2 = _make_embedding_mock(
            emb_id=EMB_ID_2,
            document_id=DOC_ID_1,
            entity_id="coverages_cov_1",
            section_type="coverages",
            entity_type="coverage",
        )

        # Mock embed
        with patch.object(
            self.service,
            "_embed_queries",
            return_value=[[0.1] * 384, [0.2] * 384],
        ):
            # Mock vector search
            self.service.vector_repo.semantic_search_multi_query.return_value = [
                (emb1, 0.25),
                (emb2, 0.35),
            ]

            # Mock reranker - returns (emb, similarity, final_score)
            self.service.reranker.rerank.return_value = [
                (emb1, 0.75, 0.92),
                (emb2, 0.65, 0.78),
            ]

            # Mock content resolution
            extraction = _make_section_extraction()
            with patch.object(
                self.service,
                "_resolve_document_names",
                return_value={DOC_ID_1: "POL_CA_00_01.pdf"},
            ), patch.object(
                self.service,
                "_resolve_content_map",
                return_value={
                    (DOC_ID_1, "coverages"): [extraction]
                },
            ), patch.object(
                self.service,
                "_resolve_entity_content",
                side_effect=[
                    "GL: $1M limit, $5K deductible",
                    "Property: $2M limit, $10K deductible",
                ],
            ), patch.object(
                self.service,
                "_extract_page_info",
                return_value=([3, 4, 5], {"start": 3, "end": 5}),
            ):
                results = await self.service.retrieve(self.query_plan)

        assert len(results) == 2
        assert isinstance(results[0], VectorSearchResult)
        assert results[0].embedding_id == EMB_ID_1
        assert results[0].similarity_score == 0.75
        assert results[0].final_score == 0.92
        assert results[0].document_name == "POL_CA_00_01.pdf"
        assert results[0].content == "GL: $1M limit, $5K deductible"
        assert results[0].page_numbers == [3, 4, 5]
        assert results[0].effective_date == date(2024, 1, 1)

    @pytest.mark.asyncio
    async def test_retrieve_passes_filters_to_search(self):
        """Should pass query plan filters to semantic_search_multi_query."""
        plan = _make_query_plan(
            target_document_ids=[DOC_ID_1],
            section_type_filters=["coverages", "exclusions"],
            entity_type_filters=["coverage", "exclusion"],
        )

        with patch.object(
            self.service,
            "_embed_queries",
            return_value=[[0.1] * 384],
        ):
            self.service.vector_repo.semantic_search_multi_query.return_value = []
            await self.service.retrieve(plan)

        call_kwargs = self.service.vector_repo.semantic_search_multi_query.call_args.kwargs
        assert call_kwargs["workflow_id"] == WORKFLOW_ID
        assert call_kwargs["document_ids"] == [DOC_ID_1]
        assert call_kwargs["section_types"] == ["coverages", "exclusions"]
        assert call_kwargs["entity_types"] == ["coverage", "exclusion"]

    @pytest.mark.asyncio
    async def test_retrieve_empty_filters_passed_as_none(self):
        """Empty filter lists should be passed as None to avoid empty IN clause."""
        plan = _make_query_plan(
            section_type_filters=[],
            entity_type_filters=[],
        )

        with patch.object(
            self.service,
            "_embed_queries",
            return_value=[[0.1] * 384],
        ):
            self.service.vector_repo.semantic_search_multi_query.return_value = []
            await self.service.retrieve(plan)

        call_kwargs = self.service.vector_repo.semantic_search_multi_query.call_args.kwargs
        assert call_kwargs["section_types"] is None
        assert call_kwargs["entity_types"] is None

    @pytest.mark.asyncio
    async def test_retrieve_passes_intent_to_reranker(self):
        """Should pass intent and entities to reranker."""
        plan = _make_query_plan(intent="ANALYSIS")
        emb = _make_embedding_mock()

        with patch.object(
            self.service,
            "_embed_queries",
            return_value=[[0.1] * 384],
        ):
            self.service.vector_repo.semantic_search_multi_query.return_value = [
                (emb, 0.3)
            ]
            self.service.reranker.rerank.return_value = [(emb, 0.7, 0.85)]

            with patch.object(
                self.service, "_resolve_results", return_value=[]
            ):
                await self.service.retrieve(plan)

        rerank_kwargs = self.service.reranker.rerank.call_args.kwargs
        assert rerank_kwargs["intent"] == "ANALYSIS"
        assert rerank_kwargs["entity_type_filters"] == ["coverage"]


# ---------------------------------------------------------------------------
# Tests: _format_entity_data
# ---------------------------------------------------------------------------


class TestFormatEntityData:
    """Tests for entity data formatting."""

    def setup_method(self):
        self.service = VectorRetrievalService.__new__(VectorRetrievalService)

    def test_format_basic_entity(self):
        """Should format key-value pairs with section prefix."""
        data = {"name": "General Liability", "limit": "$1,000,000"}
        result = self.service._format_entity_data("coverages", data)
        assert "[coverages]" in result
        assert "General Liability" in result
        assert "$1,000,000" in result

    def test_format_skips_private_keys(self):
        """Should skip keys starting with underscore."""
        data = {"_internal": "skip", "name": "GL"}
        result = self.service._format_entity_data("coverages", data)
        assert "_internal" not in result
        assert "GL" in result

    def test_format_skips_none_values(self):
        """Should skip None values."""
        data = {"name": "GL", "extra": None}
        result = self.service._format_entity_data("coverages", data)
        assert "extra" not in result

    def test_format_includes_complex_values(self):
        """Should include dict and list values in formatted output."""
        data = {"name": "GL", "nested": {"a": 1}, "items": [1, 2, 3]}
        result = self.service._format_entity_data("coverages", data)
        assert "GL" in result
        assert "nested" in result
        assert "items" in result

    def test_format_empty_data(self):
        """Should return section prefix only for empty data."""
        result = self.service._format_entity_data("coverages", {})
        assert result == "[coverages]"
