"""merge_section_entity_and_document_tables

Revision ID: h8i9j0k1l2m3
Revises: c3d4e5f6g7h8, g7h8i9j0k1l2
Create Date: 2025-12-29 22:35:00.000000

Merge migration to combine section_entity_persistence_tables and document_tables branches
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = ('c3d4e5f6g7h8', 'g7h8i9j0k1l2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration - no schema changes needed."""
    # This is a merge migration that combines two branches.
    # Both migrations have already been applied independently,
    # so no schema changes are needed here.
    pass


def downgrade() -> None:
    """Downgrade merge migration."""
    # Merge migrations typically don't have downgrades
    # as they only exist to merge branches in the migration tree.
    pass

