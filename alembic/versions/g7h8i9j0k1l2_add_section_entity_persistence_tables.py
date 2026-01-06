"""add_section_entity_persistence_tables

Revision ID: g7h8i9j0k1l2
Revises: b0d6b10e408f
Create Date: 2025-12-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, Sequence[str], None] = 'b0d6b10e408f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create section_extractions table
    op.create_table(
        'section_extractions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('section_type', sa.String(), nullable=False, comment='Section type: Declarations, Coverages, SOV, LossRun, etc.'),
        sa.Column('page_range', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Page range: {start: int, end: int}'),
        sa.Column('extracted_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Raw extracted fields from LLM (JSONB)'),
        sa.Column('confidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Confidence metrics per field'),
        sa.Column('source_chunks', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Source chunk references: {chunk_ids: [], stable_chunk_ids: []}'),
        sa.Column('pipeline_run_id', sa.String(), nullable=True),
        sa.Column('model_version', sa.String(), nullable=True, comment='LLM model version for provenance'),
        sa.Column('prompt_version', sa.String(), nullable=True, comment='Prompt template version used'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Raw section-level extraction output store'
    )
    op.create_index(op.f('ix_section_extractions_pipeline_run_id'), 'section_extractions', ['pipeline_run_id'], unique=False)
    op.create_index(op.f('ix_section_extractions_document_id_section_type'), 'section_extractions', ['document_id', 'section_type'], unique=False)

    # Create entity_mentions table
    op.create_table(
        'entity_mentions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('section_extraction_id', sa.UUID(), nullable=True),
        sa.Column('entity_type', sa.String(), nullable=False, comment='Entity type: INSURED, CARRIER, POLICY, CLAIM, etc.'),
        sa.Column('mention_text', sa.Text(), nullable=False, comment='Original text as it appears in document'),
        sa.Column('extracted_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Raw mention payload from LLM extraction'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Overall confidence (0.0-1.0)'),
        sa.Column('confidence_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Detailed confidence metrics'),
        sa.Column('source_document_chunk_id', sa.UUID(), nullable=True),
        sa.Column('source_stable_chunk_id', sa.String(), nullable=True, comment='Deterministic chunk ID for provenance'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_extraction_id'], ['section_extractions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_document_chunk_id'], ['document_chunks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        comment='Document-scoped entity mentions with ambiguity allowed'
    )
    op.create_index(op.f('ix_entity_mentions_document_id_entity_type'), 'entity_mentions', ['document_id', 'entity_type'], unique=False)

    # Create entity_evidence table
    op.create_table(
        'entity_evidence',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('canonical_entity_id', sa.UUID(), nullable=False),
        sa.Column('entity_mention_id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Evidence confidence (0.0-1.0)'),
        sa.Column('evidence_type', sa.String(), nullable=False, server_default='extracted', comment='Evidence type: extracted, inferred, human_verified'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['canonical_entity_id'], ['canonical_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entity_mention_id'], ['entity_mentions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Evidence mapping for canonical entities (explainability/audit)'
    )
    op.create_index(op.f('ix_entity_evidence_canonical_entity_id'), 'entity_evidence', ['canonical_entity_id'], unique=False)
    op.create_index(op.f('ix_entity_evidence_entity_mention_id'), 'entity_evidence', ['entity_mention_id'], unique=False)

    # Create entity_attributes table
    op.create_table(
        'entity_attributes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('canonical_entity_id', sa.UUID(), nullable=False),
        sa.Column('attribute_name', sa.String(), nullable=False, comment='Attribute name'),
        sa.Column('attribute_value', postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment='Attribute value (text or JSONB)'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Attribute confidence (0.0-1.0)'),
        sa.Column('source_document_id', sa.UUID(), nullable=True),
        sa.Column('source_entity_mention_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['canonical_entity_id'], ['canonical_entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_document_id'], ['documents.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_entity_mention_id'], ['entity_mentions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        comment='Attribute-level provenance for canonical entities'
    )

    # Create typed canonical entity tables (1:1 with canonical_entities)
    op.create_table(
        'insured_entities',
        sa.Column('id', sa.UUID(), nullable=False, comment='1:1 FK to canonical_entities.id'),
        sa.Column('canonical_name', sa.String(), nullable=False, comment='Canonical insured name'),
        sa.Column('normalized_name', sa.String(), nullable=True, comment='Normalized name for matching'),
        sa.Column('primary_address', sa.Text(), nullable=True, comment='Primary address'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Entity confidence'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['canonical_entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Typed canonical entity table for insured parties'
    )

    op.create_table(
        'carrier_entities',
        sa.Column('id', sa.UUID(), nullable=False, comment='1:1 FK to canonical_entities.id'),
        sa.Column('canonical_name', sa.String(), nullable=False, comment='Canonical carrier name'),
        sa.Column('normalized_name', sa.String(), nullable=True, comment='Normalized name for matching'),
        sa.Column('naic', sa.String(), nullable=True, comment='NAIC code'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Entity confidence'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['canonical_entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Typed canonical entity table for insurance carriers'
    )

    op.create_table(
        'policy_entities',
        sa.Column('id', sa.UUID(), nullable=False, comment='1:1 FK to canonical_entities.id'),
        sa.Column('policy_number', sa.String(), nullable=False, comment='Policy number'),
        sa.Column('effective_date', sa.Date(), nullable=True, comment='Policy effective date'),
        sa.Column('expiration_date', sa.Date(), nullable=True, comment='Policy expiration date'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Entity confidence'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['canonical_entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Typed canonical entity table for policies'
    )

    op.create_table(
        'claim_entities',
        sa.Column('id', sa.UUID(), nullable=False, comment='1:1 FK to canonical_entities.id'),
        sa.Column('claim_number', sa.String(), nullable=False, comment='Claim number'),
        sa.Column('loss_date', sa.Date(), nullable=True, comment='Loss date'),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True, comment='Entity confidence'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=False),
        sa.ForeignKeyConstraint(['id'], ['canonical_entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Typed canonical entity table for claims'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('claim_entities')
    op.drop_table('policy_entities')
    op.drop_table('carrier_entities')
    op.drop_table('insured_entities')
    op.drop_table('entity_attributes')
    op.drop_index(op.f('ix_entity_evidence_entity_mention_id'), table_name='entity_evidence')
    op.drop_index(op.f('ix_entity_evidence_canonical_entity_id'), table_name='entity_evidence')
    op.drop_table('entity_evidence')
    op.drop_index(op.f('ix_entity_mentions_document_id_entity_type'), table_name='entity_mentions')
    op.drop_table('entity_mentions')
    op.drop_index(op.f('ix_section_extractions_document_id_section_type'), table_name='section_extractions')
    op.drop_index(op.f('ix_section_extractions_pipeline_run_id'), table_name='section_extractions')
    op.drop_table('section_extractions')

