"""add semantic metadata to document chunks

Revision ID: a1b2c3d4e5f6
Revises: 3908a879744b
Create Date: 2026-02-03 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3908a879744b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add effective_section_type column for endorsement semantic projection
    op.add_column(
        'document_chunks',
        sa.Column(
            'effective_section_type',
            sa.String(),
            nullable=True,
            comment='Effective section for extraction routing (may differ from section_type for endorsements)'
        )
    )
    # Add semantic_role column for coverage/exclusion modifier tracking
    op.add_column(
        'document_chunks',
        sa.Column(
            'semantic_role',
            sa.String(),
            nullable=True,
            comment='Semantic role: coverage_modifier, exclusion_modifier, both, administrative_only, etc.'
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('document_chunks', 'semantic_role')
    op.drop_column('document_chunks', 'effective_section_type')
