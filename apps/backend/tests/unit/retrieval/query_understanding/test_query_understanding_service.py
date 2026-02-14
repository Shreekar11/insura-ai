"""Unit tests for QueryUnderstandingService."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.services.retrieval.query_understanding.service import QueryUnderstandingService
from app.schemas.query import QueryPlan


class TestQueryUnderstandingService:
    """Test suite for QueryUnderstandingService."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_workflow_docs(self):
        """Create mock workflow documents."""
        doc_1 = Mock()
        doc_1.document_id = uuid4()

        doc_2 = Mock()
        doc_2.document_id = uuid4()

        return [doc_1, doc_2]

    @pytest.fixture
    def mock_sections(self):
        """Create mock sections."""
        section_1 = Mock()
        section_1.id = uuid4()
        section_1.document_id = uuid4()
        section_1.section_type = "declarations"
        section_1.section_name = "Declarations Page"
        section_1.content = "Policy information and declarations"
        section_1.page_numbers = [1]

        section_2 = Mock()
        section_2.id = uuid4()
        section_2.document_id = uuid4()
        section_2.section_type = "coverages"
        section_2.section_name = "Coverage Limits"
        section_2.content = "Coverage details and limits"
        section_2.page_numbers = [2, 3]

        return [section_1, section_2]

    @pytest.fixture
    def mock_entities(self):
        """Create mock entities."""
        entity_1 = Mock()
        entity_1.id = uuid4()
        entity_1.document_id = uuid4()
        entity_1.entity_type = "policy"
        entity_1.entity_name = "Commercial General Liability Policy"
        entity_1.attributes = {"policy_number": "POL-12345"}
        entity_1.confidence = 0.95

        entity_2 = Mock()
        entity_2.id = uuid4()
        entity_2.document_id = uuid4()
        entity_2.entity_type = "coverage"
        entity_2.entity_name = "General Liability Coverage"
        entity_2.attributes = {"limit": "$1,000,000"}
        entity_2.confidence = 0.90

        return [entity_1, entity_2]

    @pytest.fixture
    async def service(self, mock_db_session, mock_workflow_docs, mock_sections, mock_entities):
        """Create QueryUnderstandingService with mocked dependencies."""
        with patch(
            "app.services.retrieval.query_understanding.service.WorkflowDocumentRepository"
        ) as mock_workflow_repo_class, patch(
            "app.services.retrieval.query_understanding.service.StepSectionOutputRepository"
        ) as mock_section_repo_class, patch(
            "app.services.retrieval.query_understanding.service.StepEntityOutputRepository"
        ) as mock_entity_repo_class:

            # Setup mock repositories
            mock_workflow_repo = Mock()
            mock_workflow_repo.get_by_workflow_id = AsyncMock(return_value=mock_workflow_docs)
            mock_workflow_repo_class.return_value = mock_workflow_repo

            mock_section_repo = Mock()
            mock_section_repo.get_by_document_and_workflow = AsyncMock(return_value=mock_sections)
            mock_section_repo_class.return_value = mock_section_repo

            mock_entity_repo = Mock()
            mock_entity_repo.get_by_document_and_workflow = AsyncMock(return_value=mock_entities)
            mock_entity_repo_class.return_value = mock_entity_repo

            # Create service
            service = QueryUnderstandingService(mock_db_session)

            # Store mocks for assertion
            service._mock_workflow_repo = mock_workflow_repo
            service._mock_section_repo = mock_section_repo
            service._mock_entity_repo = mock_entity_repo

            yield service

    @pytest.mark.asyncio
    async def test_understand_query_qa_intent(self, service):
        """Test query understanding with QA intent."""
        query = "What is the policy number?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should return QueryPlan
        assert isinstance(result, QueryPlan)

        # Should classify as QA
        assert result.intent == "QA"
        assert result.traversal_depth == 1

        # Should preserve original query
        assert result.original_query == query

        # Should have expanded queries
        assert isinstance(result.expanded_queries, list)
        assert len(result.expanded_queries) >= 1
        assert query in result.expanded_queries

        # Should have workflow context
        assert result.workflow_context is not None
        assert result.workflow_context.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_understand_query_analysis_intent(self, service):
        """Test query understanding with ANALYSIS intent."""
        query = "Compare the coverage limits between policies"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should classify as ANALYSIS
        assert result.intent == "ANALYSIS"
        assert result.traversal_depth == 2

        # Should have section filters appropriate for analysis
        assert isinstance(result.section_type_filters, list)

    @pytest.mark.asyncio
    async def test_understand_query_audit_intent(self, service):
        """Test query understanding with AUDIT intent."""
        query = "Show me the evidence for this coverage"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should classify as AUDIT
        assert result.intent == "AUDIT"
        assert result.traversal_depth == 3

    @pytest.mark.asyncio
    async def test_understand_query_with_entities(self, service):
        """Test query understanding extracts entities correctly."""
        query = "What is the coverage limit for policy POL-12345 effective 01/15/2024?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should extract policy number
        assert "POL-12345" in result.extracted_entities.policy_numbers

        # Should extract date
        assert len(result.extracted_entities.dates) > 0

    @pytest.mark.asyncio
    async def test_understand_query_with_abbreviations(self, service):
        """Test query understanding expands abbreviations."""
        query = "What is the BI coverage?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should have expanded queries
        assert len(result.expanded_queries) > 1

        # Should include expansion with "bodily injury"
        assert any("bodily injury" in q.lower() for q in result.expanded_queries)

    @pytest.mark.asyncio
    async def test_understand_query_fetches_workflow_context(self, service):
        """Test that workflow context is fetched from repositories."""
        query = "What is the coverage?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should have called workflow repository
        service._mock_workflow_repo.get_by_workflow_id.assert_called_once_with(workflow_id)

        # Should have workflow context
        assert result.workflow_context is not None
        assert result.workflow_context.document_count > 0
        assert len(result.workflow_context.sections) > 0
        assert len(result.workflow_context.entities) > 0

    @pytest.mark.asyncio
    async def test_understand_query_with_target_documents(self, service, mock_workflow_docs):
        """Test query understanding with specific target documents."""
        query = "What is the coverage?"
        workflow_id = uuid4()
        target_doc_id = mock_workflow_docs[0].document_id

        result = await service.understand_query(
            query, workflow_id, target_document_ids=[target_doc_id]
        )

        # Should have target documents set
        assert result.target_document_ids == [target_doc_id]

        # Context should be filtered to target documents
        assert result.workflow_context.document_count > 0

    @pytest.mark.asyncio
    async def test_understand_query_derives_section_filters(self, service):
        """Test that section type filters are derived correctly."""
        # QA intent should prioritize declarations, coverages
        query_qa = "What is the policy number?"
        workflow_id = uuid4()

        result_qa = await service.understand_query(query_qa, workflow_id)
        assert "declarations" in result_qa.section_type_filters
        assert "coverages" in result_qa.section_type_filters

        # ANALYSIS intent should prioritize coverages, endorsements
        query_analysis = "Compare the endorsements"
        result_analysis = await service.understand_query(query_analysis, workflow_id)
        assert "coverages" in result_analysis.section_type_filters
        assert "endorsements" in result_analysis.section_type_filters

        # AUDIT intent should prioritize endorsements, claims
        query_audit = "Show me the evidence for this claim"
        result_audit = await service.understand_query(query_audit, workflow_id)
        assert "endorsements" in result_audit.section_type_filters

    @pytest.mark.asyncio
    async def test_understand_query_derives_entity_filters(self, service):
        """Test that entity type filters are derived correctly."""
        # QA intent should prioritize policy, organization, coverage
        query_qa = "What is the coverage?"
        workflow_id = uuid4()

        result_qa = await service.understand_query(query_qa, workflow_id)
        assert "policy" in result_qa.entity_type_filters
        assert "organization" in result_qa.entity_type_filters
        assert "coverage" in result_qa.entity_type_filters

        # ANALYSIS intent should prioritize coverage, endorsement, exclusion
        query_analysis = "Analyze the endorsement impact"
        result_analysis = await service.understand_query(query_analysis, workflow_id)
        assert "coverage" in result_analysis.entity_type_filters
        assert "endorsement" in result_analysis.entity_type_filters

    @pytest.mark.asyncio
    async def test_understand_query_handles_no_documents(self, service):
        """Test query understanding when workflow has no documents."""
        # Mock empty workflow
        service._mock_workflow_repo.get_by_workflow_id = AsyncMock(return_value=[])

        query = "What is the coverage?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should still return QueryPlan
        assert isinstance(result, QueryPlan)

        # Workflow context should be empty
        assert result.workflow_context.document_count == 0
        assert len(result.workflow_context.sections) == 0
        assert len(result.workflow_context.entities) == 0

    @pytest.mark.asyncio
    async def test_understand_query_section_hints_from_query(self, service):
        """Test that section hints from query are used in filters."""
        query = "Show me the endorsements"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should extract "endorsements" as section hint
        assert "endorsements" in result.extracted_entities.section_hints

        # Should include in section filters
        assert "endorsements" in result.section_type_filters

    @pytest.mark.asyncio
    async def test_understand_query_coverage_types_in_entity_filters(self, service):
        """Test that extracted coverage types influence entity filters."""
        query = "What is the GL coverage limit?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should extract GL as coverage type
        assert "general liability" in result.extracted_entities.coverage_types

        # Should include "coverage" in entity filters
        assert "coverage" in result.entity_type_filters

    @pytest.mark.asyncio
    async def test_understand_query_complete_pipeline(self, service):
        """Test complete pipeline with realistic query."""
        query = "Compare the BI limits for policy POL-12345 with the endorsements"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Intent classification
        assert result.intent == "ANALYSIS"  # "compare" keyword
        assert result.traversal_depth == 2

        # Entity extraction
        assert "POL-12345" in result.extracted_entities.policy_numbers
        assert "endorsements" in result.extracted_entities.section_hints

        # Query expansion
        assert len(result.expanded_queries) > 1
        assert any("bodily injury" in q.lower() for q in result.expanded_queries)

        # Workflow context
        assert result.workflow_context is not None
        assert result.workflow_context.document_count > 0

        # Filters
        assert len(result.section_type_filters) > 0
        assert len(result.entity_type_filters) > 0

    @pytest.mark.asyncio
    async def test_understand_query_empty_query(self, service):
        """Test understanding of empty query."""
        query = ""
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # Should return QueryPlan with defaults
        assert isinstance(result, QueryPlan)
        assert result.intent == "QA"  # Default intent
        assert result.original_query == ""

    @pytest.mark.asyncio
    async def test_understand_query_logging(self, service):
        """Test that appropriate logging occurs."""
        query = "What is the coverage?"
        workflow_id = uuid4()

        with patch("app.services.retrieval.query_understanding.service.LOGGER") as mock_logger:
            await service.understand_query(query, workflow_id)

            # Should log various stages
            assert mock_logger.info.call_count >= 5  # At least 5 log statements

    @pytest.mark.asyncio
    async def test_understand_query_section_repo_calls(self, service, mock_workflow_docs):
        """Test that section repository is called for each document."""
        query = "What is the coverage?"
        workflow_id = uuid4()

        await service.understand_query(query, workflow_id)

        # Should call section repo for each document
        assert service._mock_section_repo.get_by_document_and_workflow.call_count == len(
            mock_workflow_docs
        )

    @pytest.mark.asyncio
    async def test_understand_query_entity_repo_calls(self, service, mock_workflow_docs):
        """Test that entity repository is called for each document."""
        query = "What is the coverage?"
        workflow_id = uuid4()

        await service.understand_query(query, workflow_id)

        # Should call entity repo for each document
        assert service._mock_entity_repo.get_by_document_and_workflow.call_count == len(
            mock_workflow_docs
        )

    @pytest.mark.asyncio
    async def test_understand_query_filter_validation(self, service):
        """Test that derived filters are validated against valid types."""
        query = "What is the coverage?"
        workflow_id = uuid4()

        result = await service.understand_query(query, workflow_id)

        # All section filters should be valid
        from app.services.retrieval.constants import VALID_SECTION_TYPES

        for section_filter in result.section_type_filters:
            assert (
                section_filter in VALID_SECTION_TYPES
            ), f"Invalid section filter: {section_filter}"

        # All entity filters should be valid
        from app.services.retrieval.constants import VALID_ENTITY_TYPES

        for entity_filter in result.entity_type_filters:
            assert (
                entity_filter in VALID_ENTITY_TYPES
            ), f"Invalid entity filter: {entity_filter}"

    @pytest.mark.asyncio
    async def test_understand_query_preserves_query_structure(self, service):
        """Test that QueryPlan preserves all query components."""
        query = "Compare GL coverage for policy POL-12345"
        workflow_id = uuid4()
        target_doc_id = uuid4()

        result = await service.understand_query(
            query, workflow_id, target_document_ids=[target_doc_id]
        )

        # Should preserve all components
        assert result.original_query == query
        assert result.workflow_context.workflow_id == workflow_id
        assert result.target_document_ids == [target_doc_id]
        assert isinstance(result.extracted_entities, object)
        assert isinstance(result.expanded_queries, list)
        assert isinstance(result.section_type_filters, list)
        assert isinstance(result.entity_type_filters, list)
