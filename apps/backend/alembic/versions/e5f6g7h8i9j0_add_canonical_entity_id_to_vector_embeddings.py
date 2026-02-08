"""add_canonical_entity_id_to_vector_embeddings

Revision ID: e5f6g7h8i9j0
Revises: fd3022570b79
Create Date: 2026-02-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6g7h8i9j0'
down_revision: Union[str, Sequence[str], None] = 'fd3022570b79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add canonical_entity_id FK to vector_embeddings."""
    # Add canonical_entity_id column with FK to canonical_entities
    op.add_column(
        'vector_embeddings',
        sa.Column(
            'canonical_entity_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='FK to canonical entity for vector↔graph bridge'
        )
    )

    # Create FK constraint
    op.create_foreign_key(
        'fk_vector_embeddings_canonical_entity_id',
        'vector_embeddings',
        'canonical_entities',
        ['canonical_entity_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Create index on canonical_entity_id for efficient lookups
    op.create_index(
        'ix_vector_embeddings_canonical_entity_id',
        'vector_embeddings',
        ['canonical_entity_id']
    )


def downgrade() -> None:
    """Downgrade schema - remove canonical_entity_id FK from vector_embeddings."""
    # Drop index
    op.drop_index('ix_vector_embeddings_canonical_entity_id', table_name='vector_embeddings')

    # Drop FK constraint
    op.drop_constraint('fk_vector_embeddings_canonical_entity_id', 'vector_embeddings', type_='foreignkey')

    # Drop column
    op.drop_column('vector_embeddings', 'canonical_entity_id')
