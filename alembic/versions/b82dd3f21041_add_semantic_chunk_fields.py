"""add_semantic_chunk_fields

Revision ID: b82dd3f21041
Revises: e133764c790e
Create Date: 2026-01-06 17:16:39.544529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b82dd3f21041'
down_revision: Union[str, Sequence[str], None] = 'e133764c790e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add semantic fields
    # subsection_type already exists in previous migration
    op.add_column('document_chunks', sa.Column('semantic_unit_id', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('coverage_letter', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('target_coverage', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('location_id', sa.String(), nullable=True))
    op.add_column('document_chunks', sa.Column('claim_id', sa.String(), nullable=True))

    # Add cross-reference fields (JSONB)
    op.add_column('document_chunks', sa.Column('references_to', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=True))
    op.add_column('document_chunks', sa.Column('referenced_by', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=True))

    # Add indices
    op.create_index('idx_document_chunks_references', 'document_chunks', ['references_to'], postgresql_using='gin')
    op.create_index('idx_document_chunks_referenced_by', 'document_chunks', ['referenced_by'], postgresql_using='gin')
    # index on subsection_type. Check if it exists? The previous migration didn't seemingly create an index on it, just the column.
    # The requirement says: CREATE INDEX idx_document_chunks_subsection ON document_chunks (subsection_type);
    op.create_index('idx_document_chunks_subsection', 'document_chunks', ['subsection_type'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_document_chunks_subsection', table_name='document_chunks')
    op.drop_index('idx_document_chunks_referenced_by', table_name='document_chunks')
    op.drop_index('idx_document_chunks_references', table_name='document_chunks')
    op.drop_column('document_chunks', 'referenced_by')
    op.drop_column('document_chunks', 'references_to')
    op.drop_column('document_chunks', 'claim_id')
    op.drop_column('document_chunks', 'location_id')
    op.drop_column('document_chunks', 'target_coverage')
    op.drop_column('document_chunks', 'coverage_letter')
    op.drop_column('document_chunks', 'semantic_unit_id')

