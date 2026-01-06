"""reverse_add_semantic_chunk_fields

Revision ID: e4888e902562
Revises: b82dd3f21041
Create Date: 2026-01-06 21:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4888e902562'
down_revision: Union[str, Sequence[str], None] = 'b82dd3f21041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Reverse the semantic chunk fields migration."""

    # Drop indices
    op.drop_index('idx_document_chunks_subsection', table_name='document_chunks')
    op.drop_index('idx_document_chunks_referenced_by', table_name='document_chunks')
    op.drop_index('idx_document_chunks_references', table_name='document_chunks')

    # Drop JSONB cross-reference fields
    op.drop_column('document_chunks', 'referenced_by')
    op.drop_column('document_chunks', 'references_to')

    # Drop semantic fields
    op.drop_column('document_chunks', 'claim_id')
    op.drop_column('document_chunks', 'location_id')
    op.drop_column('document_chunks', 'target_coverage')
    op.drop_column('document_chunks', 'coverage_letter')
    op.drop_column('document_chunks', 'semantic_unit_id')


def downgrade() -> None:
    """Re-apply semantic chunk fields."""

    # Re-add semantic fields
    op.add_column('document_chunks', sa.Column('semantic_unit_id', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('coverage_letter', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('target_coverage', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('location_id', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('claim_id', sa.String(), nullable=True))

    # Re-add JSONB fields
    op.add_column(
        'document_chunks',
        sa.Column(
            'references_to',
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            server_default='[]',
            nullable=True,
        ),
    )
    op.add_column(
        'document_chunks',
        sa.Column(
            'referenced_by',
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            server_default='[]',
            nullable=True,
        ),
    )

    # Re-create indices
    op.create_index(
        'idx_document_chunks_references',
        'document_chunks',
        ['references_to'],
        postgresql_using='gin',
    )
    op.create_index(
        'idx_document_chunks_referenced_by',
        'document_chunks',
        ['referenced_by'],
        postgresql_using='gin',
    )
    op.create_index(
        'idx_document_chunks_subsection',
        'document_chunks',
        ['subsection_type'],
    )
