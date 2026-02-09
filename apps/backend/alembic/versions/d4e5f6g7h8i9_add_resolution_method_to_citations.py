"""add resolution_method to citations

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6g7h8i9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6g7h8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add resolution_method column to citations table."""
    op.add_column(
        'citations',
        sa.Column(
            'resolution_method',
            sa.String(50),
            nullable=True,
            comment='How citation was resolved: direct_text_match, semantic_chunk_match, placeholder'
        )
    )


def downgrade() -> None:
    """Remove resolution_method from citations."""
    op.drop_column('citations', 'resolution_method')
