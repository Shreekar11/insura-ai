"""Unit tests for section and entity persistence repositories."""

import pytest
from uuid import uuid4, UUID
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Document,
    SectionExtraction,
    EntityMention,
    EntityEvidence,
    CanonicalEntity,
    DocumentChunk,
)
from app.repositories.section_extraction_repository import SectionExtractionRepository
from app.repositories.entity_mention_repository import EntityMentionRepository
from app.repositories.entity_evidence_repository import EntityEvidenceRepository


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock(spec=AsyncSession)
    session.add = Mock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def test_document():
    """Create a test document."""
    document = Document(
        id=uuid4(),
        file_path="/test/path.pdf",
        mime_type="application/pdf",
        page_count=10,
        status="uploaded",
    )
    session.add(document)
    await session.flush()
    return document


@pytest.fixture
def test_chunk(test_document):
    """Create a test document chunk."""
    chunk = DocumentChunk(
        id=uuid4(),
        document_id=test_document.id,
        page_number=1,
        chunk_index=0,
        raw_text="Test chunk text",
        token_count=100,
        section_type="declarations",
        stable_chunk_id=f"doc_{test_document.id}_p1_c0",
    )
    session.add(chunk)
    await session.flush()
    return chunk


@pytest.mark.asyncio
async def test_create_section_extraction(
    mock_session,
    test_document,
):
    """Test creating a section extraction."""
    # Mock the flush to set id on the object
    def mock_flush():
        extraction = mock_session.add.call_args[0][0]
        extraction.id = uuid4()
        extraction.created_at = datetime.now()
        return AsyncMock()
    
    mock_session.flush.side_effect = mock_flush
    
    repo = SectionExtractionRepository(mock_session)
    
    extracted_fields = {
        "policy_number": "POL123456",
        "insured_name": "Test Insured",
        "effective_date": "2024-01-01",
    }
    
    extraction = await repo.create_section_extraction(
        document_id=test_document.id,
        section_type="declarations",
        extracted_fields=extracted_fields,
        page_range={"start": 1, "end": 3},
        confidence={"overall": 0.95},
        source_chunks={"stable_chunk_ids": ["chunk1", "chunk2"]},
        pipeline_run_id="run_123",
        model_version="qwen3:8b",
        prompt_version="v1",
    )
    
    # Verify repository was called correctly
    assert mock_session.add.called
    added_extraction = mock_session.add.call_args[0][0]
    assert isinstance(added_extraction, SectionExtraction)
    assert added_extraction.document_id == test_document.id
    assert added_extraction.section_type == "declarations"
    assert added_extraction.extracted_fields == extracted_fields
    assert added_extraction.page_range == {"start": 1, "end": 3}
    assert added_extraction.confidence == {"overall": 0.95}
    assert added_extraction.source_chunks == {"stable_chunk_ids": ["chunk1", "chunk2"]}
    assert added_extraction.pipeline_run_id == "run_123"
    assert added_extraction.model_version == "qwen3:8b"
    assert added_extraction.prompt_version == "v1"
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_get_section_extractions_by_document(
    mock_session,
    test_document,
):
    """Test getting section extractions by document."""
    # Mock query results
    extraction1 = SectionExtraction(
        id=uuid4(),
        document_id=test_document.id,
        section_type="declarations",
        extracted_fields={"field1": "value1"},
    )
    extraction2 = SectionExtraction(
        id=uuid4(),
        document_id=test_document.id,
        section_type="coverages",
        extracted_fields={"field2": "value2"},
    )
    
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = [extraction1, extraction2]
    mock_session.execute.return_value = mock_result
    
    repo = SectionExtractionRepository(mock_session)
    
    # Get all extractions
    extractions = await repo.get_by_document(test_document.id)
    assert len(extractions) == 2
    assert {e.id for e in extractions} == {extraction1.id, extraction2.id}
    
    # Get by section type
    mock_result.scalars.return_value.all.return_value = [extraction1]
    declarations = await repo.get_by_document(test_document.id, section_type="declarations")
    assert len(declarations) == 1
    assert declarations[0].id == extraction1.id


@pytest.mark.asyncio
async def test_create_entity_mention(
    mock_session,
    test_document,
    test_chunk,
):
    """Test creating an entity mention."""
    def mock_flush():
        mention = mock_session.add.call_args[0][0]
        mention.id = uuid4()
        mention.created_at = datetime.now()
        return AsyncMock()
    
    mock_session.flush.side_effect = mock_flush
    
    repo = EntityMentionRepository(mock_session)
    
    extracted_fields = {
        "name": "Test Insured",
        "address": "123 Main St",
    }
    
    mention = await repo.create_entity_mention(
        document_id=test_document.id,
        entity_type="INSURED",
        mention_text="Test Insured",
        extracted_fields=extracted_fields,
        confidence=Decimal("0.95"),
        source_document_chunk_id=test_chunk.id,
        source_stable_chunk_id=test_chunk.stable_chunk_id,
    )
    
    # Verify repository was called correctly
    assert mock_session.add.called
    added_mention = mock_session.add.call_args[0][0]
    assert isinstance(added_mention, EntityMention)
    assert added_mention.document_id == test_document.id
    assert added_mention.entity_type == "INSURED"
    assert added_mention.mention_text == "Test Insured"
    assert added_mention.extracted_fields == extracted_fields
    assert added_mention.confidence == Decimal("0.95")
    assert added_mention.source_document_chunk_id == test_chunk.id
    assert added_mention.source_stable_chunk_id == test_chunk.stable_chunk_id
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_create_entity_mention_with_section_extraction(
    mock_session,
    test_document,
):
    """Test creating an entity mention linked to section extraction."""
    section_extraction_id = uuid4()
    
    def mock_flush():
        obj = mock_session.add.call_args[0][0]
        obj.id = uuid4()
        obj.created_at = datetime.now()
        if isinstance(obj, SectionExtraction):
            obj.id = section_extraction_id
        return AsyncMock()
    
    mock_session.flush.side_effect = mock_flush
    
    # Create section extraction first
    section_repo = SectionExtractionRepository(mock_session)
    section_extraction = await section_repo.create_section_extraction(
        document_id=test_document.id,
        section_type="declarations",
        extracted_fields={"field": "value"},
    )
    
    # Create entity mention linked to section extraction
    mention_repo = EntityMentionRepository(mock_session)
    mention = await mention_repo.create_entity_mention(
        document_id=test_document.id,
        entity_type="POLICY",
        mention_text="POL123456",
        extracted_fields={"policy_number": "POL123456"},
        section_extraction_id=section_extraction.id,
    )
    
    # Verify the mention was created with correct section extraction link
    added_mention = [call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], EntityMention)][-1]
    assert added_mention.section_extraction_id == section_extraction.id
    assert added_mention.document_id == test_document.id


@pytest.mark.asyncio
async def test_get_entity_mentions_by_document(
    mock_session,
    test_document,
):
    """Test getting entity mentions by document."""
    mention1 = EntityMention(
        id=uuid4(),
        document_id=test_document.id,
        entity_type="INSURED",
        mention_text="Insured 1",
        extracted_fields={"name": "Insured 1"},
    )
    mention2 = EntityMention(
        id=uuid4(),
        document_id=test_document.id,
        entity_type="CARRIER",
        mention_text="Carrier 1",
        extracted_fields={"name": "Carrier 1"},
    )
    
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = [mention1, mention2]
    mock_session.execute.return_value = mock_result
    
    repo = EntityMentionRepository(mock_session)
    
    # Get all mentions
    mentions = await repo.get_by_document(test_document.id)
    assert len(mentions) == 2
    
    # Get by entity type
    mock_result.scalars.return_value.all.return_value = [mention1]
    insured_mentions = await repo.get_by_document(test_document.id, entity_type="INSURED")
    assert len(insured_mentions) == 1
    assert insured_mentions[0].id == mention1.id


@pytest.mark.asyncio
async def test_create_entity_evidence(
    mock_session,
    test_document,
):
    """Test creating entity evidence."""
    canonical_entity_id = uuid4()
    mention_id = uuid4()
    
    def mock_flush():
        obj = mock_session.add.call_args[0][0]
        obj.id = uuid4()
        obj.created_at = datetime.now()
        if isinstance(obj, EntityMention):
            obj.id = mention_id
        return AsyncMock()
    
    mock_session.flush.side_effect = mock_flush
    
    # Create entity mention
    mention_repo = EntityMentionRepository(mock_session)
    mention = await mention_repo.create_entity_mention(
        document_id=test_document.id,
        entity_type="POLICY",
        mention_text="POL123456",
        extracted_fields={"policy_number": "POL123456"},
    )
    
    # Create evidence
    evidence_repo = EntityEvidenceRepository(mock_session)
    evidence = await evidence_repo.create_entity_evidence(
        canonical_entity_id=canonical_entity_id,
        entity_mention_id=mention.id,
        document_id=test_document.id,
        confidence=Decimal("0.95"),
        evidence_type="extracted",
    )
    
    # Verify evidence was created correctly
    assert mock_session.add.called
    added_evidence = [call[0][0] for call in mock_session.add.call_args_list if isinstance(call[0][0], EntityEvidence)][-1]
    assert isinstance(added_evidence, EntityEvidence)
    assert added_evidence.canonical_entity_id == canonical_entity_id
    assert added_evidence.entity_mention_id == mention.id
    assert added_evidence.document_id == test_document.id
    assert added_evidence.confidence == Decimal("0.95")
    assert added_evidence.evidence_type == "extracted"
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_get_entity_evidence_by_canonical_entity(
    mock_session,
    test_document,
):
    """Test getting evidence records by canonical entity."""
    canonical_entity_id = uuid4()
    evidence1_id = uuid4()
    evidence2_id = uuid4()
    
    evidence1 = EntityEvidence(
        id=evidence1_id,
        canonical_entity_id=canonical_entity_id,
        entity_mention_id=uuid4(),
        document_id=test_document.id,
    )
    evidence2 = EntityEvidence(
        id=evidence2_id,
        canonical_entity_id=canonical_entity_id,
        entity_mention_id=uuid4(),
        document_id=test_document.id,
    )
    
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = [evidence1, evidence2]
    mock_session.execute.return_value = mock_result
    
    evidence_repo = EntityEvidenceRepository(mock_session)
    
    # Get evidence by canonical entity
    evidence_records = await evidence_repo.get_by_canonical_entity(canonical_entity_id)
    assert len(evidence_records) == 2
    assert {e.id for e in evidence_records} == {evidence1_id, evidence2_id}


@pytest.mark.asyncio
async def test_create_batch_entity_mentions(
    mock_session,
    test_document,
):
    """Test creating multiple entity mentions in batch."""
    def mock_flush():
        for call in mock_session.add.call_args_list:
            obj = call[0][0]
            if isinstance(obj, EntityMention):
                obj.id = uuid4()
                obj.created_at = datetime.now()
        return AsyncMock()
    
    mock_session.flush.side_effect = mock_flush
    
    repo = EntityMentionRepository(mock_session)
    
    mentions_data = [
        {
            "document_id": test_document.id,
            "entity_type": "INSURED",
            "mention_text": "Insured 1",
            "extracted_fields": {"name": "Insured 1"},
        },
        {
            "document_id": test_document.id,
            "entity_type": "CARRIER",
            "mention_text": "Carrier 1",
            "extracted_fields": {"name": "Carrier 1"},
        },
    ]
    
    mentions = await repo.create_batch(mentions_data)
    
    assert len(mentions) == 2
    assert mock_session.add.call_count == 2
    assert all(isinstance(m, EntityMention) for m in mentions)
    assert {m.entity_type for m in mentions} == {"INSURED", "CARRIER"}
    assert mock_session.flush.called


@pytest.mark.asyncio
async def test_create_batch_entity_evidence(
    mock_session,
    test_document,
):
    """Test creating multiple entity evidence records in batch."""
    canonical_entity_id = uuid4()
    mention1_id = uuid4()
    mention2_id = uuid4()
    
    def mock_flush():
        for call in mock_session.add.call_args_list:
            obj = call[0][0]
            obj.id = uuid4()
            obj.created_at = datetime.now()
            if isinstance(obj, EntityMention):
                if len([c for c in mock_session.add.call_args_list if isinstance(c[0][0], EntityMention)]) == 1:
                    obj.id = mention1_id
                else:
                    obj.id = mention2_id
        return AsyncMock()
    
    mock_session.flush.side_effect = mock_flush
    
    # Create mentions
    mention_repo = EntityMentionRepository(mock_session)
    mention1 = await mention_repo.create_entity_mention(
        document_id=test_document.id,
        entity_type="POLICY",
        mention_text="POL123456",
        extracted_fields={},
    )
    mention2 = await mention_repo.create_entity_mention(
        document_id=test_document.id,
        entity_type="POLICY",
        mention_text="POL123456",
        extracted_fields={},
    )
    
    # Create evidence in batch
    evidence_repo = EntityEvidenceRepository(mock_session)
    evidence_data = [
        {
            "canonical_entity_id": canonical_entity_id,
            "entity_mention_id": mention1.id,
            "document_id": test_document.id,
            "evidence_type": "extracted",
        },
        {
            "canonical_entity_id": canonical_entity_id,
            "entity_mention_id": mention2.id,
            "document_id": test_document.id,
            "evidence_type": "extracted",
        },
    ]
    
    evidence_records = await evidence_repo.create_batch(evidence_data)
    
    assert len(evidence_records) == 2
    assert mock_session.add.call_count >= 4  # 2 mentions + 2 evidence records
    assert all(isinstance(e, EntityEvidence) for e in evidence_records)
    assert all(e.canonical_entity_id == canonical_entity_id for e in evidence_records)
    assert mock_session.flush.called

