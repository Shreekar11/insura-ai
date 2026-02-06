"""add source_chunk_id to vector_embeddings

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-02-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add source_chunk_id FK to vector_embeddings for chunk-level embeddings."""
    op.add_column(
        'vector_embeddings',
        sa.Column(
            'source_chunk_id',
            sa.UUID(),
            nullable=True,
            comment='FK to document_chunks for chunk-level embeddings'
        )
    )

    op.create_foreign_key(
        'fk_vector_embeddings_source_chunk',
        'vector_embeddings',
        'document_chunks',
        ['source_chunk_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Index for efficient lookups of chunk embeddings by source chunk
    op.create_index(
        'ix_vector_embeddings_source_chunk_id',
        'vector_embeddings',
        ['source_chunk_id'],
        postgresql_where=sa.text("source_chunk_id IS NOT NULL")
    )

    # Index for filtering by entity_type (chunk vs entity embeddings)
    op.create_index(
        'ix_vector_embeddings_entity_type',
        'vector_embeddings',
        ['entity_type']
    )


def downgrade() -> None:
    """Remove source_chunk_id from vector_embeddings."""
    op.drop_index('ix_vector_embeddings_entity_type', table_name='vector_embeddings')
    op.drop_index('ix_vector_embeddings_source_chunk_id', table_name='vector_embeddings')
    op.drop_constraint('fk_vector_embeddings_source_chunk', 'vector_embeddings', type_='foreignkey')
    op.drop_column('vector_embeddings', 'source_chunk_id')
